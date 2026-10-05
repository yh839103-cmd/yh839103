"""AI 模型串接（Anthropic Claude API）。"""
from __future__ import annotations

import os

DEFAULT_SYSTEM_PROMPT = (
    "你是一個友善、簡潔的 LINE 聊天助理。"
    "請使用繁體中文回答，除非使用者用其他語言提問。"
    "回答盡量精簡，適合在手機上閱讀，避免使用 Markdown 表格。"
)


class ClaudeLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 system_prompt: str | None = None, max_tokens: int = 1024):
        import anthropic  # 延後匯入，讓核心邏輯測試不需要安裝 SDK

        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
        self.system_prompt = system_prompt or os.getenv(
            "SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
        self.max_tokens = max_tokens

    def __call__(self, history: list[dict]) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=history,
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
