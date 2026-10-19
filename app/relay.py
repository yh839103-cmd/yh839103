"""「查 …」：轉給使用者電腦上的本地模型（W7 轉接站 line-search-relay.mjs）。

bot 本體一直在 Render 上；只有「查 」「查：」「搜尋 」開頭的訊息，
會經由 Cloudflare 通道送到電腦上的轉接站，由本地模型（Ollama gemma4）上網搜尋後回答。

設定（Render → Environment）：
  SEARCH_RELAY_URL  轉接站印出來的 https://….trycloudflare.com（每次重開都會換，換了改這裡就好）
  SEARCH_RELAY_KEY  轉接站的通關密碼（放在標頭 x-relay-key，不放網址）
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger("line-ai-bot")

# 「查 」「查：」「搜尋 」開頭才轉給本地模型；「查一下明天…」照舊交給 Gemini
SEARCH_PREFIX = re.compile(r"^(?:查|搜尋)[\s:：]+([\s\S]+)$")
TIMEOUT = 50  # LINE 的回覆期限有限，等太久就改說連不到

NOT_SET_TEXT = "這支 bot 還沒接上本地模型（Render 要設定 SEARCH_RELAY_URL 和 SEARCH_RELAY_KEY）。"
OFFLINE_TEXT = ("🔌 本地模型現在連不到（或等超過 50 秒）：電腦關了、轉接站的視窗被關掉，"
                "或通道換了網址（Render 的 SEARCH_RELAY_URL 要改成新的）。")
BAD_KEY_TEXT = "🔒 轉接站說密碼不對：檢查 Render 的 SEARCH_RELAY_KEY。"
BUSY_TEXT = "⏳ 本地模型正在回答上一題，等十幾秒再問一次。"


def match(text: str) -> str | None:
    """是「查 …」就回傳要查的問題，不是就回傳 None。"""
    m = SEARCH_PREFIX.match((text or "").strip())
    return m.group(1).strip() if m else None


def ask(question: str) -> str:
    """問轉接站；任何錯誤都轉成給使用者看的文字，不丟例外。"""
    url = os.getenv("SEARCH_RELAY_URL", "").strip().rstrip("/")
    key = os.getenv("SEARCH_RELAY_KEY", "").strip()
    if not url or not key:
        return NOT_SET_TEXT
    req = urllib.request.Request(
        url + "/ask",
        data=json.dumps({"question": question}).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-relay-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            code, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except Exception as e:  # noqa: BLE001 — 連不到、逾時
        log.warning("連不到轉接站：%s", e)
        return OFFLINE_TEXT
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        data = {}
    if code == 401:
        return BAD_KEY_TEXT
    if code == 429:
        return BUSY_TEXT
    if code != 200 or not data.get("answer"):
        log.warning("轉接站回應 %s：%s", code, (raw or b"")[:200])
        return f"🔌 本地模型這次沒答出來（{code}）：{data.get('error') or '通道可能已經關了，或網址換了'}"
    reply = "🔎 " + data["answer"]
    sources = data.get("sources") or []
    if sources:
        reply += "\n\n來源：\n" + "\n".join("• " + s.get("url", "") for s in sources)
    else:
        reply += "\n\nℹ️ 這題模型沒有上網查，只憑記憶回答，請自己再核對。"
    return reply + f"\n（本地模型 {data.get('seconds', '?')} 秒）"
