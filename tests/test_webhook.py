"""端對端測試：用正確簽章送假的 LINE webhook 進伺服器，檢查會回覆什麼。

需要 line-bot-sdk（requirements.txt 已包含）；沒有安裝時自動略過。
"""
import base64
import hashlib
import hmac
import json
import os
from unittest import mock

try:
    import linebot.v3  # noqa: F401
    HAS_SDK = True
except ImportError:
    HAS_SDK = False

SECRET = "test-secret"
os.environ.setdefault("LINE_CHANNEL_SECRET", SECRET)
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")


def _event(message: dict) -> dict:
    return {
        "type": "message", "mode": "active", "timestamp": 1760000000000,
        "webhookEventId": "01TEST", "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "U123"}, "replyToken": "rt-1",
        "message": message,
    }


class _SyncThread:
    """讓背景執行緒在測試中直接同步執行。"""
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def _post(event: dict):
    """送出一個 webhook，回傳 (HTTP 狀態碼, 回覆給 LINE 的訊息 JSON 列表)。"""
    import app.main as m
    body = json.dumps({"destination": "Ubot", "events": [event]})
    secret = os.environ["LINE_CHANNEL_SECRET"].encode()
    sig = base64.b64encode(hmac.new(secret, body.encode(), hashlib.sha256).digest()).decode()
    api = mock.MagicMock()
    with mock.patch.object(m, "MessagingApi", api), \
         mock.patch.object(m.threading, "Thread", _SyncThread):
        resp = m.app.test_client().post(
            "/callback", data=body, headers={"X-Line-Signature": sig,
                                             "Content-Type": "application/json"})
    calls = api.return_value.reply_message.call_args_list
    msgs = [json.loads(x.to_json()) for c in calls for x in c[0][0].messages]
    return resp.status_code, msgs


def test_sticker_gets_hint_with_quick_replies():
    if not HAS_SDK:
        return
    from app.core import NON_TEXT_TEXT, QUICK_REPLIES
    status, msgs = _post(_event({"type": "sticker", "id": "1", "quoteToken": "q",
                                 "packageId": "446", "stickerId": "1988",
                                 "stickerResourceType": "STATIC"}))
    assert status == 200
    assert msgs[0]["text"] == NON_TEXT_TEXT
    items = msgs[0]["quickReply"]["items"]
    assert [i["action"]["label"] for i in items] == [l for l, _ in QUICK_REPLIES]


def test_image_gets_hint():
    if not HAS_SDK:
        return
    from app.core import NON_TEXT_TEXT
    status, msgs = _post(_event({"type": "image", "id": "2", "quoteToken": "q",
                                 "contentProvider": {"type": "line"}}))
    assert status == 200 and msgs[0]["text"] == NON_TEXT_TEXT


def test_text_answer_has_quick_replies_on_last_message_only():
    if not HAS_SDK:
        return
    import app.main as m
    long_answer = ("一" * 4000 + "\n") * 2      # 超過 5000 字，會切成 2 則
    with mock.patch.object(m.chat, "llm", lambda history: long_answer):
        status, msgs = _post(_event({"type": "text", "id": "3", "quoteToken": "q",
                                     "text": "你好"}))
    assert status == 200 and len(msgs) == 2
    assert "quickReply" not in msgs[0] or msgs[0]["quickReply"] is None
    assert len(msgs[1]["quickReply"]["items"]) >= 2


def test_help_command_via_button_text():
    if not HAS_SDK:
        return
    from app.core import HELP_TEXT
    status, msgs = _post(_event({"type": "text", "id": "4", "quoteToken": "q",
                                 "text": "說明"}))
    assert status == 200 and msgs[0]["text"] == HELP_TEXT


def test_bad_signature_is_rejected():
    if not HAS_SDK:
        return
    import app.main as m
    resp = m.app.test_client().post("/callback", data="{}",
                                    headers={"X-Line-Signature": "wrong"})
    assert resp.status_code == 400
