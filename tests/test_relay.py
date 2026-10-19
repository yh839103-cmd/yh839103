"""「查 …」轉給本地模型轉接站的測試（不真的連網）。"""
import io
import json
import urllib.error
from unittest import mock

from app import relay
from app.core import ChatService, ConversationStore


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def __call__(self, history):
        self.calls += 1
        return "gemini"


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _env(monkeypatch, url="https://abc.trycloudflare.com/", key="secret"):
    monkeypatch.setenv("SEARCH_RELAY_URL", url)
    monkeypatch.setenv("SEARCH_RELAY_KEY", key)


def test_match_prefixes():
    assert relay.match("查 今年諾貝爾獎") == "今年諾貝爾獎"
    assert relay.match("查：台北天氣") == "台北天氣"
    assert relay.match("搜尋 東華大學") == "東華大學"
    assert relay.match("查一下明天的天氣") is None   # 沒有空格：照舊交給 Gemini
    assert relay.match("你好") is None


def test_not_configured(monkeypatch):
    monkeypatch.delenv("SEARCH_RELAY_URL", raising=False)
    monkeypatch.delenv("SEARCH_RELAY_KEY", raising=False)
    assert relay.ask("x") == relay.NOT_SET_TEXT


def test_success_sends_key_in_header_and_lists_sources(monkeypatch):
    _env(monkeypatch)
    body = json.dumps({"answer": "Francis Halzen", "seconds": 12,
                       "sources": [{"title": "t", "url": "https://a.example"}]}).encode()
    with mock.patch("urllib.request.urlopen", return_value=_Resp(200, body)) as m:
        out = relay.ask("2026 諾貝爾物理獎")
    req = m.call_args[0][0]
    assert req.full_url == "https://abc.trycloudflare.com/ask"   # 尾巴的 / 會去掉
    assert req.get_header("X-relay-key") == "secret"
    assert "secret" not in req.full_url                          # 密碼不放網址
    assert json.loads(req.data)["question"] == "2026 諾貝爾物理獎"
    assert out.startswith("🔎 Francis Halzen")
    assert "• https://a.example" in out and "12 秒" in out


def test_no_sources_warns(monkeypatch):
    _env(monkeypatch)
    body = json.dumps({"answer": "玉山", "seconds": 3, "sources": []}).encode()
    with mock.patch("urllib.request.urlopen", return_value=_Resp(200, body)):
        assert "沒有上網查" in relay.ask("台灣最高的山")


def test_wrong_key(monkeypatch):
    _env(monkeypatch)
    err = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b'{"error":"bad"}'))
    with mock.patch("urllib.request.urlopen", side_effect=err):
        assert relay.ask("x") == relay.BAD_KEY_TEXT


def test_offline(monkeypatch):
    _env(monkeypatch)
    with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        assert relay.ask("x") == relay.OFFLINE_TEXT


def test_chat_service_routes_search_without_gemini():
    llm, asked = FakeLLM(), []
    store = ConversationStore()
    svc = ChatService(llm, store, search=lambda q: asked.append(q) or "🔎 答案")
    assert svc.handle("u1", "查 今天新聞") == ["🔎 答案"]
    assert asked == ["今天新聞"] and llm.calls == 0
    assert store.history("u1") == []          # 查詢不進對話記憶
    assert svc.handle("u1", "你好") == ["gemini"] and llm.calls == 1
