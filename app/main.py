"""LINE Webhook 伺服器（Flask + line-bot-sdk v3）。"""
from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict

from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
)
from linebot.v3.webhooks import (
    AudioMessageContent,
    FileMessageContent,
    FollowEvent,
    ImageMessageContent,
    LocationMessageContent,
    MessageEvent,
    StickerMessageContent,
    TextMessageContent,
    VideoMessageContent,
)

from app.core import HELP_TEXT, NON_TEXT_TEXT, ChatService, ConversationStore
from app.line_messages import build_messages
from app.llm import GeminiLLM

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("line-ai-bot")

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"].strip())
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"].strip())

chat = ChatService(
    llm=GeminiLLM(),
    store=ConversationStore(
        max_turns=int(os.getenv("MAX_TURNS", "10")),
        ttl_seconds=int(os.getenv("SESSION_TTL", "3600")),
    ),
)

app = Flask(__name__)


@app.get("/")
def health():
    return "OK"


@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    log.info("收到 LINE webhook（%d bytes）", len(body))
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        log.warning("簽章驗證失敗")
        abort(400)
    return "OK"


def _reply(reply_token: str, texts: list[str]) -> None:
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=build_messages(texts),  # 最後一則附快速回覆按鈕
            )
        )


def _push(to: str, texts: list[str]) -> None:
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=to, messages=build_messages(texts)))


def _process(user_id: str, chat_id: str | None, reply_token: str, text: str) -> None:
    try:
        if chat_id:  # 只有一對一聊天支援「輸入中」動畫
            with ApiClient(configuration) as api_client:
                # 最長 60 秒（第一版只有 20 秒，AI 想比較久時動畫會先消失，看起來像罷工）
                MessagingApi(api_client).show_loading_animation(
                    ShowLoadingAnimationRequest(chat_id=chat_id, loading_seconds=60))
    except Exception:  # noqa: BLE001
        log.debug("無法顯示讀取動畫", exc_info=True)
    answer = chat.handle(user_id, text)   # 內部已處理所有 AI 錯誤，一定會有回覆文字
    log.info("AI 回覆完成，共 %d 則", len(answer))
    try:
        _reply(reply_token, answer)
        log.info("已回覆 LINE")
        return
    except Exception as e:  # noqa: BLE001
        # 最常見原因：AI 想太久，reply token 已過期。改用推播，確保使用者一定收得到。
        log.warning("回覆失敗（%s），改用推播訊息", str(e)[:200])
    try:
        _push(user_id, answer)
        log.info("已用推播回覆 LINE")
    except Exception:  # noqa: BLE001
        log.exception("推播也失敗")


# LINE 在伺服器沒及時回應時可能重送同一個事件，用事件 ID 避免重複回答
_seen_events: OrderedDict[str, None] = OrderedDict()
_seen_lock = threading.Lock()


def _is_duplicate(event_id: str | None) -> bool:
    if not event_id:
        return False
    with _seen_lock:
        if event_id in _seen_events:
            return True
        _seen_events[event_id] = None
        while len(_seen_events) > 1000:
            _seen_events.popitem(last=False)
        return False


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent):
    if _is_duplicate(getattr(event, "webhook_event_id", None)):
        log.info("重複的事件，略過：%s", event.webhook_event_id)
        return
    log.info("收到文字訊息")
    src = event.source
    user_id = getattr(src, "user_id", None) or "anonymous"
    # 群組 / 聊天室用群組 ID 作為對話記憶的 key，讓大家共享上下文
    session_key = getattr(src, "group_id", None) or getattr(src, "room_id", None) or user_id
    chat_id = user_id if src.type == "user" else None
    # 在背景處理，讓 webhook 立即回 200，避免 LINE 平台逾時重送
    threading.Thread(
        target=_process,
        args=(session_key, chat_id, event.reply_token, event.message.text),
        daemon=True,
    ).start()


@handler.add(FollowEvent)
def on_follow(event: FollowEvent):
    _reply(event.reply_token, [HELP_TEXT])


# 第一版收到貼圖、圖片等非文字訊息時完全不回應，看起來像當機；
# 改善版改成立刻回覆提示（不需要呼叫 AI）。
NON_TEXT_TYPES = (
    StickerMessageContent, ImageMessageContent, VideoMessageContent,
    AudioMessageContent, FileMessageContent, LocationMessageContent,
)


def on_non_text(event: MessageEvent):
    log.info("收到非文字訊息：%s", event.message.type)
    try:
        _reply(event.reply_token, [NON_TEXT_TEXT])
    except Exception:  # noqa: BLE001
        log.exception("回覆非文字訊息失敗")


for _type in NON_TEXT_TYPES:
    handler.add(MessageEvent, message=_type)(on_non_text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
