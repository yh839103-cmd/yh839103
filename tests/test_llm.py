import io
import json
from unittest import mock

from app.llm import GeminiLLM


def make():
    return GeminiLLM(api_key="k", model="gemini-flash-latest", system_prompt="sys")


def test_build_body_maps_roles():
    body = make().build_body([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    assert body["system_instruction"]["parts"][0]["text"] == "sys"
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert body["contents"][1]["parts"][0]["text"] == "hello"


def test_call_sends_key_and_parses_text():
    reply = {"candidates": [{"content": {"parts": [{"text": "你好"}, {"text": "！"}]}}]}
    fake = mock.MagicMock()
    fake.__enter__.return_value = io.BytesIO(json.dumps(reply).encode())
    with mock.patch("urllib.request.urlopen", return_value=fake) as op:
        assert make()([{"role": "user", "content": "hi"}]) == "你好！"
    req = op.call_args[0][0]
    assert req.get_header("X-goog-api-key") == "k"
    assert "gemini-flash-latest:generateContent" in req.full_url



def test_empty_reply_raises():
    try:
        GeminiLLM.parse({"candidates": [{"content": {"parts": []}}]})
    except ValueError:
        return
    raise AssertionError("expected ValueError")
