"""AI 模型串接（Google Gemini API，免費方案可用）。

只用 Python 內建的 urllib，不需要額外安裝套件。
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

DEFAULT_SYSTEM_PROMPT = (
    "你是一個友善、簡潔的 LINE 聊天助理。"
    "請使用繁體中文回答，除非使用者用其他語言提問。"
    "回答盡量精簡，適合在手機上閱讀，避免使用 Markdown 表格。"
)
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_CODES = {429, 500, 502, 503, 504}   # 伺服器忙線／暫時錯誤，值得重試
log = logging.getLogger("line-ai-bot")


class GeminiLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 system_prompt: str | None = None, max_tokens: int = 1024,
                 timeout: int = 20, fallback_model: str | None = None):
        self.api_key = (api_key or os.environ["GEMINI_API_KEY"]).strip()
        # gemini-flash-latest 會自動指向 Google 最新的 Flash 模型
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        # 主模型忙線時改用的輕量模型
        self.fallback_model = fallback_model or os.getenv(
            "GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
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

    def _request(self, model: str, body: bytes) -> str:
        req = urllib.request.Request(
            API_URL.format(model=model),
            data=body,
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self.api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return self.parse(json.load(resp))

    def __call__(self, history: list[dict]) -> str:
        body = json.dumps(self.build_body(history)).encode("utf-8")
        # 主模型試 2 次，再換備用模型試 1 次；整體控制在約 1 分鐘內
        plan = [self.model, self.model, self.fallback_model]
        last_error = None
        for attempt, model in enumerate(plan):
            if attempt:
                time.sleep(2)
            try:
                return self._request(model, body)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                last_error = RuntimeError(f"Gemini API 錯誤 {e.code}（{model}）：{detail}")
                if e.code not in RETRY_CODES:
                    raise last_error from None
                log.warning("Gemini 忙線 %s（%s），重試中", e.code, model)
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = RuntimeError(f"Gemini 連線失敗（{model}）：{e}")
                log.warning("Gemini 連線失敗（%s），重試中", model)
        raise last_error
