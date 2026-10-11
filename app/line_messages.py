"""把文字包成 LINE 訊息，並在最後一則加上快速回覆按鈕。"""
from __future__ import annotations

from linebot.v3.messaging import MessageAction, QuickReply, QuickReplyItem, TextMessage

from app.core import QUICK_REPLIES


def quick_reply() -> QuickReply:
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label=label, text=text))
        for label, text in QUICK_REPLIES
    ])


def build_messages(texts: list[str]) -> list[TextMessage]:
    """快速回覆按鈕只會顯示在最後一則訊息上，所以只加在最後一則。"""
    messages = [TextMessage(text=t) for t in texts]
    if messages:
        messages[-1].quick_reply = quick_reply()
    return messages
