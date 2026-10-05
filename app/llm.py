"""AI 模型串接（Google Gemini API，免費方案可用）。

只用 Python 內建的 urllib，不需要額外安裝套件。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_SYSTEM_PROMPT = (
    "你是一個友善、簡潔的 LINE 聊天助理。"
    "請使用繁體中文回答，除非使用者用其他語言提問。"
    "回答盡量精簡，適合在手機上閱讀，避免使用 Markdown 表格。"
)
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 system_prompt: str | None = None, max_tokens: int = 1024,
                 timeout: int = 50):
        self.api_key = (api_key or os.environ["GEMINI_API_KEY"]).strip()
        # gemini-flash-latest 會自動指向 Google 最新的 Flash 模型
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.system_prompt = system_prompt or os.getenv(
            "SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
        self.max_tokens = max_tokens
        self.timeout = timeout

    def build_body(self, history: list[dict]) -> dict:
        return {
            "system_instruction": {"parts": [{"text": self.system_prompt}]},
            "contents": [
                {"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]}
                for m in history
            ],
            "generationConfig": {"maxOutputTokens": self.max_tokens},
        }

    @staticmethod
    def parse(data: dict) -> str:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise ValueError("Gemini 沒有回傳文字")
        return text

    def __call__(self, history: list[dict]) -> str:
        req = urllib.request.Request(
            API_URL.format(model=self.model),
            data=json.dumps(self.build_body(history)).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return self.parse(json.load(resp))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:1000]
            raise RuntimeError(f"Gemini API 錯誤 {e.code}：{detail}") from None
