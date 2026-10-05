"""AI 模型串接（Google Gemini API，免費方案可用）。

只用 Python 內建的 urllib，不需要額外安裝套件。
AI 可以自己決定要不要呼叫 app/tools.py 裡的免費查詢工具（維基百科、天氣）。
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from app import tools

DEFAULT_SYSTEM_PROMPT = (
    "你是一個友善、可靠的 LINE 聊天助理，使用者主要在台灣。\n"
    "1. 使用繁體中文與台灣慣用詞（例如：軟體、網路、影片），除非使用者用其他語言提問。\n"
    "2. 正確性優先：回答前先想清楚。不確定的事情要直接說「我不確定」，"
    "絕對不要編造數字、日期、人名、地址或網址。\n"
    "3. 你有兩個查詢工具：search_wikipedia（查知識）和 get_weather（查天氣）。"
    "遇到人物、地點、歷史、數據等事實性問題，只要不是百分之百確定就先查；"
    "用查到的資料回答時，在最後簡短註明來源（例如「資料來源：維基百科」）。\n"
    "4. 你無法查新聞、股價、店家營業時間、交通、商品價格等即時資訊；"
    "遇到這類問題要說明資訊可能過時，並建議到官方網站確認。\n"
    "5. 問題不明確時，先用一句話反問釐清，不要亂猜。\n"
    "6. 醫療、法律、投資問題只提供一般資訊，並建議諮詢專業人士。\n"
    "7. 回答精簡、分點清楚，適合在手機上閱讀；不要使用 Markdown 表格、# 標題或 ** 粗體。"
)
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_CODES = {429, 500, 502, 503, 504}   # 伺服器忙線／暫時錯誤，值得重試
MAX_TOOL_ROUNDS = 3
TAIWAN_TZ = timezone(timedelta(hours=8))
log = logging.getLogger("line-ai-bot")


def _env_list(name: str, default: str) -> list[str]:
    return [m.strip() for m in os.getenv(name, default).split(",") if m.strip()]


class GeminiLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 system_prompt: str | None = None, max_tokens: int = 4096,
                 timeout: int = 20, fallback_models: list[str] | None = None,
                 use_tools: bool | None = None):
        self.api_key = (api_key or os.environ["GEMINI_API_KEY"]).strip()
        # gemini-flash-latest 會自動指向 Google 最新、免費可用的 Flash 模型
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        # 主模型忙線時依序改用的模型（每個模型的免費額度是分開算的）
        self.fallback_models = fallback_models or _env_list(
            "GEMINI_FALLBACK_MODEL", "gemini-3.7-flash,gemini-3.5-flash-lite")
        self.system_prompt = system_prompt or os.getenv(
            "SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
        self.max_tokens = max_tokens
        self.timeout = timeout
        # 溫度越低越穩定、越不容易亂掰（0～2）
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.4"))
        self.use_tools = (os.getenv("ENABLE_TOOLS", "true").lower() != "false"
                          if use_tools is None else use_tools)

    # ---------- 組請求 ----------
    def _system_text(self) -> str:
        # 告訴 AI 今天的日期，避免它以為還是訓練資料的年份
        now = datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d %H:%M（%A）")
        return f"{self.system_prompt}\n\n現在時間（台灣）：{now}"

    @staticmethod
    def to_contents(history: list[dict]) -> list[dict]:
        return [
            {"role": "model" if m["role"] == "assistant" else "user",
             "parts": [{"text": m["content"]}]}
            for m in history
        ]

    def build_body(self, history_or_contents: list[dict], with_tools: bool | None = None) -> dict:
        contents = (history_or_contents
                    if history_or_contents and "parts" in history_or_contents[0]
                    else self.to_contents(history_or_contents))
        body = {
            "system_instruction": {"parts": [{"text": self._system_text()}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": self.max_tokens,
                                 "temperature": self.temperature},
        }
        if self.use_tools if with_tools is None else with_tools:
            body["tools"] = [{"functionDeclarations": tools.DECLARATIONS}]
        return body

    # ---------- 解析回應 ----------
    @staticmethod
    def parse(data: dict) -> str:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        if not text:
            raise ValueError("Gemini 沒有回傳文字")
        return text

    # ---------- 送出（含重試、換模型） ----------
    def _request(self, model: str, body: dict) -> dict:
        req = urllib.request.Request(
            API_URL.format(model=model),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self.api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    def _post(self, body: dict) -> tuple[dict, str]:
        """主模型試 2 次，再依序試備用模型；回傳 (回應, 實際使用的模型)。"""
        plan = [self.model, self.model, *self.fallback_models]
        last_error: Exception | None = None
        for attempt, model in enumerate(plan):
            if attempt:
                time.sleep(1.5)
            try:
                return self._request(model, body), model
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                last_error = RuntimeError(f"Gemini API 錯誤 {e.code}（{model}）：{detail}")
                if e.code == 400 and "tools" in body:
                    # 萬一這個模型不接受工具，拿掉工具再試，至少要回答得出來
                    log.warning("模型 %s 不接受工具，改用純文字模式", model)
                    body = {k: v for k, v in body.items() if k != "tools"}
                    continue
                if e.code == 404 and model != self.model:
                    continue  # 備用模型名稱不存在，換下一個
                if e.code not in RETRY_CODES:
                    raise last_error from None
                log.warning("Gemini 忙線 %s（%s），重試中", e.code, model)
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = RuntimeError(f"Gemini 連線失敗（{model}）：{e}")
                log.warning("Gemini 連線失敗（%s），重試中", model)
        raise last_error  # type: ignore[misc]

    def __call__(self, history: list[dict]) -> str:
        contents = self.to_contents(history)
        for _ in range(MAX_TOOL_ROUNDS):
            data, model = self._post(self.build_body(contents))
            content = data["candidates"][0].get("content", {})
            calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
            if not calls:
                answer = self.parse(data)
                log.info("Gemini 回答完成（模型：%s）", model)
                return answer
            # AI 要查資料：原樣保留它的這一步（含思考簽章），再把查詢結果交回去
            contents.append(content)
            responses = []
            for c in calls:
                fr = {"name": c["name"], "response": tools.run(c["name"], c.get("args", {}))}
                if "id" in c:
                    fr["id"] = c["id"]
                responses.append({"functionResponse": fr})
            contents.append({"role": "user", "parts": responses})
        # 查太多次還沒結論：不給工具，請它直接用已查到的資料回答
        data, model = self._post(self.build_body(contents, with_tools=False))
        log.info("Gemini 回答完成（模型：%s）", model)
        return self.parse(data)
