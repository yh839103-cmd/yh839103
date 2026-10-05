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
    sys_text = body["system_instruction"]["parts"][0]["text"]
    assert sys_text.startswith("sys") and "現在時間（台灣）" in sys_text
    assert body["generationConfig"]["temperature"] == 0.4
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


def _http_error(code):
    import urllib.error
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(b'{"error":"busy"}'))


def _ok(text):
    fake = mock.MagicMock()
    fake.__enter__.return_value = io.BytesIO(json.dumps(
        {"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode())
    return fake


def test_retries_then_falls_back_on_503():
    llm = GeminiLLM(api_key="k", model="main", fallback_model="lite")
    side = [_http_error(503), _http_error(503), _ok("備用回答")]
    with mock.patch("urllib.request.urlopen", side_effect=side) as op, \
         mock.patch("time.sleep"):
        assert llm([{"role": "user", "content": "hi"}]) == "備用回答"
    urls = [c[0][0].full_url for c in op.call_args_list]
    assert "main:" in urls[0] and "main:" in urls[1] and "lite:" in urls[2]


def test_bad_key_does_not_retry():
    llm = GeminiLLM(api_key="k", model="main", fallback_model="lite")
    with mock.patch("urllib.request.urlopen", side_effect=[_http_error(400)]) as op:
        try:
            llm([{"role": "user", "content": "hi"}])
        except RuntimeError as e:
            assert "400" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
    assert op.call_count == 1
