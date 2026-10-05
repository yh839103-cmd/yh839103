import time

from app.core import (
    HELP_TEXT,
    RESET_TEXT,
    ChatService,
    ConversationStore,
    parse_command,
    split_message,
)


class FakeLLM:
    def __init__(self, reply="你好！", fail=False):
        self.reply, self.fail, self.calls = reply, fail, []

    def __call__(self, history):
        self.calls.append(list(history))
        if self.fail:
            raise RuntimeError("boom")
        return self.reply


def test_parse_command():
    assert parse_command("/help") == "help"
    assert parse_command("  /RESET ") == "reset"
    assert parse_command("重新開始") == "reset"
    assert parse_command("今天天氣如何") is None


def test_store_keeps_recent_turns_and_starts_with_user():
    s = ConversationStore(max_turns=2)
    for i in range(5):
        s.append("u", "user", f"q{i}")
        s.append("u", "assistant", f"a{i}")
    h = s.history("u")
    assert len(h) == 4
    assert h[0] == {"role": "user", "content": "q3"}


def test_store_ttl_expires():
    s = ConversationStore(ttl_seconds=0)
    s.append("u", "user", "hi")
    time.sleep(0.01)
    assert s.history("u") == []


def test_users_are_isolated():
    s = ConversationStore()
    s.append("a", "user", "A")
    assert s.history("b") == []


def test_split_message_short():
    assert split_message("hi") == ["hi"]


def test_split_message_long_prefers_newlines_and_limits():
    text = ("一" * 30 + "\n") * 30  # 約 930 字，超過 5 段 x 100 字
    parts = split_message(text, limit=100, max_parts=5)
    assert all(len(p) <= 100 for p in parts)
    assert len(parts) <= 5
    assert parts[-1].endswith("…")


def test_chat_flow_with_memory():
    llm = FakeLLM("回覆")
    svc = ChatService(llm, ConversationStore())
    assert svc.handle("u", "第一句") == ["回覆"]
    svc.handle("u", "第二句")
    assert [m["content"] for m in llm.calls[-1]] == ["第一句", "回覆", "第二句"]


def test_help_and_reset():
    llm = FakeLLM()
    store = ConversationStore()
    svc = ChatService(llm, store)
    svc.handle("u", "hello")
    assert svc.handle("u", "/help") == [HELP_TEXT]
    assert svc.handle("u", "/reset") == [RESET_TEXT]
    assert store.history("u") == []
    assert len(llm.calls) == 1


def test_llm_failure_returns_friendly_message_and_rolls_back():
    store = ConversationStore()
    svc = ChatService(FakeLLM("ok"), store)
    svc.handle("u", "q1")
    svc.llm = FakeLLM(fail=True)
    out = svc.handle("u", "q2")
    assert "稍後" in out[0]
    assert [m["content"] for m in store.history("u")] == ["q1", "ok"]
