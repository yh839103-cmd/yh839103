"""與 LINE SDK 無關的核心邏輯：對話記憶、指令處理、訊息切段。

這一層不依賴任何外部套件，方便單元測試。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

LINE_TEXT_LIMIT = 5000      # LINE 單則文字訊息上限
LINE_MAX_MESSAGES = 5       # 一次 reply 最多 5 則訊息

HELP_TEXT = (
    "嗨！我是 AI 聊天助理 🤖\n"
    "直接傳訊息給我就能聊天。\n\n"
    "可用指令：\n"
    "/help  顯示說明\n"
    "/reset 清除對話記憶，重新開始"
)
RESET_TEXT = "好的，已清除我們的對話記憶，可以重新開始了 ✨"


@dataclass
class _Session:
    history: deque = field(default_factory=deque)
    last_active: float = field(default_factory=time.time)


class ConversationStore:
    """以使用者 ID 為 key 的記憶體內對話紀錄（thread-safe）。

    - max_turns：保留最近幾輪（一輪 = 使用者 + 助理各一則）
    - ttl_seconds：閒置超過這段時間就自動忘記
    """

    def __init__(self, max_turns: int = 10, ttl_seconds: int = 3600):
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def _get(self, user_id: str) -> _Session:
        now = time.time()
        s = self._sessions.get(user_id)
        if s is None or now - s.last_active > self.ttl_seconds:
            s = _Session()
            self._sessions[user_id] = s
        s.last_active = now
        return s

    def history(self, user_id: str) -> list[dict]:
        with self._lock:
            return list(self._get(user_id).history)

    def append(self, user_id: str, role: str, content: str) -> None:
        with self._lock:
            h = self._get(user_id).history
            h.append({"role": role, "content": content})
            while len(h) > self.max_turns * 2:
                h.popleft()
            # AI API 要求第一則必須是 user
            while h and h[0]["role"] != "user":
                h.popleft()

    def reset(self, user_id: str) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)


def parse_command(text: str) -> str | None:
    """回傳指令名稱（help / reset），不是指令則回傳 None。"""
    t = text.strip().lower()
    if t in ("/help", "/start", "說明", "幫助"):
        return "help"
    if t in ("/reset", "/clear", "重新開始", "清除"):
        return "reset"
    return None


def split_message(text: str, limit: int = LINE_TEXT_LIMIT,
                  max_parts: int = LINE_MAX_MESSAGES) -> list[str]:
    """把長文字切成符合 LINE 限制的多段，盡量在換行處斷開。"""
    text = text.strip() or "（沒有內容）"
    parts: list[str] = []
    while text and len(parts) < max_parts:
        if len(text) <= limit:
            parts.append(text)
            text = ""
            break
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:  # 超過最大則數，最後一段截斷
        last = parts[-1]
        parts[-1] = last[: limit - 1] + "…"
    return parts


class ChatService:
    """串接 AI 模型與對話記憶。llm 是一個可呼叫物件：llm(history) -> str"""

    def __init__(self, llm, store: ConversationStore):
        self.llm = llm
        self.store = store

    def handle(self, user_id: str, text: str) -> list[str]:
        cmd = parse_command(text)
        if cmd == "help":
            return [HELP_TEXT]
        if cmd == "reset":
            self.store.reset(user_id)
            return [RESET_TEXT]

        self.store.append(user_id, "user", text)
        try:
            answer = self.llm(self.store.history(user_id))
        except Exception:  # noqa: BLE001 — 任何 AI 錯誤都不該讓 webhook 失敗
            logging.getLogger("line-ai-bot").exception("呼叫 AI 失敗")
            # 移除這次的提問，避免留下沒有回覆的 user 訊息
            h = self.store.history(user_id)
            self.store.reset(user_id)
            for m in h[:-1]:
                self.store.append(user_id, m["role"], m["content"])
            return ["抱歉，我現在有點忙不過來 😵 請稍後再試一次。"]
        self.store.append(user_id, "assistant", answer)
        return split_message(answer)
