"""讓 AI 可以自己呼叫的免費查詢工具（不需要任何金鑰）。

- search_wikipedia：查中文維基百科
- get_weather：用 Open-Meteo 查即時天氣與 3 天預報
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

log = logging.getLogger("line-ai-bot")
UA = {"User-Agent": "line-ai-bot/1.0 (https://github.com/yh839103-cmd/yh839103)"}
TIMEOUT = 8

# 給 Gemini 看的工具說明（function declarations）
DECLARATIONS = [
    {
        "name": "search_wikipedia",
        "description": (
            "查詢中文維基百科，取得人物、地點、歷史、科學、作品、組織等知識的摘要。"
            "回答事實性問題前，若不是百分之百確定，就先用這個工具查證。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要查的關鍵字，越精準越好，例如「台北101」"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_weather",
        "description": "查詢某個城市現在的天氣，以及今天起 3 天的天氣預報。",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市的英文名稱，例如 Taipei、Kaohsiung、Tokyo"},
            },
            "required": ["city"],
        },
    },
]


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def search_wikipedia(query: str) -> dict:
    api = "https://zh.wikipedia.org/w/api.php"
    found = _get_json(api, {
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": 3, "format": "json",
    })
    titles = [r["title"] for r in found.get("query", {}).get("search", [])]
    if not titles:
        return {"result": f"維基百科找不到「{query}」的相關條目"}
    pages = _get_json(api, {
        "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "exchars": 1200, "titles": "|".join(titles), "format": "json",
    }).get("query", {}).get("pages", {})
    articles = []
    for p in pages.values():
        text = (p.get("extract") or "").strip()
        if text:
            title = p.get("title", "")
            articles.append({
                "title": title,
                "summary": text,
                "url": "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            })
    return {"source": "維基百科", "articles": articles}


WEATHER_CODES = {
    0: "晴", 1: "大致晴朗", 2: "多雲", 3: "陰", 45: "霧", 48: "霧",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
    66: "凍雨", 67: "凍雨", 71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "陣雨", 81: "陣雨", 82: "強陣雨", 85: "陣雪", 86: "強陣雪",
    95: "雷雨", 96: "雷雨伴冰雹", 99: "強雷雨伴冰雹",
}


def get_weather(city: str) -> dict:
    geo = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                    {"name": city, "count": 1, "language": "zh", "format": "json"})
    if not geo.get("results"):
        return {"result": f"找不到城市「{city}」，請改用英文城市名稱"}
    place = geo["results"][0]
    data = _get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 3,
    })
    cur = data.get("current", {})
    daily = data.get("daily", {})
    days = [
        {
            "date": d,
            "weather": WEATHER_CODES.get(daily["weather_code"][i], "未知"),
            "max_c": daily["temperature_2m_max"][i],
            "min_c": daily["temperature_2m_min"][i],
            "rain_chance_pct": daily["precipitation_probability_max"][i],
        }
        for i, d in enumerate(daily.get("time", []))
    ]
    return {
        "source": "Open-Meteo",
        "place": f"{place.get('name', city)}（{place.get('country', '')}）",
        "now": {
            "weather": WEATHER_CODES.get(cur.get("weather_code"), "未知"),
            "temp_c": cur.get("temperature_2m"),
            "feels_like_c": cur.get("apparent_temperature"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "wind_kmh": cur.get("wind_speed_10m"),
        },
        "forecast": days,
    }


FUNCTIONS = {"search_wikipedia": search_wikipedia, "get_weather": get_weather}


def run(name: str, args: dict) -> dict:
    """執行 AI 要求的工具；任何錯誤都轉成文字告訴 AI，不讓整個回答失敗。"""
    fn = FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"沒有這個工具：{name}"}
    try:
        log.info("執行工具 %s %s", name, args)
        return fn(**(args or {}))
    except Exception as e:  # noqa: BLE001
        log.warning("工具 %s 失敗：%s", name, e)
        return {"error": f"查詢失敗：{e}"}
