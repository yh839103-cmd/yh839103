import io
import json
from unittest import mock

from app.llm import GeminiLLM


def make():
    return GeminiLLM(api_key="k", model="gemini-flash-latest", system_prompt="sys", use_tools=False)


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
    llm = GeminiLLM(api_key="k", model="main", fallback_models=["lite"], use_tools=False)
    side = [_http_error(503), _http_error(503), _ok("備用回答")]
    with mock.patch("urllib.request.urlopen", side_effect=side) as op, \
         mock.patch("time.sleep"):
        assert llm([{"role": "user", "content": "hi"}]) == "備用回答"
    urls = [c[0][0].full_url for c in op.call_args_list]
    assert "main:" in urls[0] and "main:" in urls[1] and "lite:" in urls[2]


def test_bad_key_does_not_retry():
    llm = GeminiLLM(api_key="k", model="main", fallback_models=["lite"], use_tools=False)
    with mock.patch("urllib.request.urlopen", side_effect=[_http_error(400)]) as op:
        try:
            llm([{"role": "user", "content": "hi"}])
        except RuntimeError as e:
            assert "400" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
    assert op.call_count == 1



def test_tools_declared_when_enabled():
    body = GeminiLLM(api_key="k", system_prompt="s", use_tools=True).build_body(
        [{"role": "user", "content": "hi"}])
    names = [d["name"] for d in body["tools"][0]["functionDeclarations"]]
    assert names == ["search_wikipedia", "get_weather", "search_web"]


def _resp(parts):
    fake = mock.MagicMock()
    fake.__enter__.return_value = io.BytesIO(json.dumps(
        {"candidates": [{"content": {"role": "model", "parts": parts}}]}).encode())
    return fake


def test_tool_call_loop_runs_tool_and_returns_answer():
    llm = GeminiLLM(api_key="k", model="main", fallback_models=["lite"], use_tools=True)
    call = {"functionCall": {"name": "get_weather", "args": {"city": "Taipei"}, "id": "c1"},
            "thoughtSignature": "sig"}
    side = [_resp([call]), _resp([{"text": "台北今天晴，28 度"}])]
    gw = mock.MagicMock(return_value={"now": {"temp_c": 28}})
    with mock.patch("urllib.request.urlopen", side_effect=side) as op, \
         mock.patch.dict("app.tools.FUNCTIONS", {"get_weather": gw}):
        assert llm([{"role": "user", "content": "台北天氣"}]) == "台北今天晴，28 度"
    gw.assert_called_once_with(city="Taipei")
    second = json.loads(op.call_args_list[1][0][0].data)
    assert second["contents"][1]["parts"][0]["thoughtSignature"] == "sig"
    fr = second["contents"][2]["parts"][0]["functionResponse"]
    assert fr["id"] == "c1" and fr["response"]["now"]["temp_c"] == 28


def test_tool_error_is_reported_not_raised():
    from app import tools
    with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
        out = tools.run("search_wikipedia", {"query": "台北101"})
    assert "error" in out
    assert "error" in tools.run("nope", {})


def test_wikipedia_parsing():
    from app import tools
    search = {"query": {"search": [{"title": "台北101"}]}}
    pages = {"query": {"pages": {"1": {"title": "台北101", "extract": "台北101是摩天大樓。"}}}}
    with mock.patch("app.tools._get_json", side_effect=[search, pages]):
        out = tools.search_wikipedia("台北101")
    assert out["articles"][0]["summary"].startswith("台北101")
    assert out["articles"][0]["url"].startswith("https://zh.wikipedia.org/wiki/")


def test_weather_parsing():
    from app import tools
    geo = {"results": [{"name": "台北", "country": "台灣", "latitude": 25, "longitude": 121}]}
    fc = {"current": {"temperature_2m": 28, "weather_code": 0},
          "daily": {"time": ["2026-10-05"], "weather_code": [61], "temperature_2m_max": [30],
                    "temperature_2m_min": [24], "precipitation_probability_max": [70]}}
    with mock.patch("app.tools._get_json", side_effect=[geo, fc]):
        out = tools.get_weather("Taipei")
    assert out["now"]["weather"] == "晴" and out["forecast"][0]["weather"] == "小雨"


def test_search_web_without_key_returns_error():
    from app import tools
    with mock.patch.dict("os.environ", {"TAVILY_API_KEY": ""}):
        out = tools.search_web("最新新聞")
    assert out == {"error": "搜尋功能尚未設定金鑰"}


def test_search_web_calls_tavily_with_bearer_and_parses_results():
    from app import tools
    reply = {
        "answer": "台北 10 月 12 日高溫 32 度",
        "results": [
            {"title": "台北高溫", "url": "https://example.com/1",
             "content": "台北今天高溫" * 100},
            {"title": "新聞", "url": "https://example.com/2"},
        ],
    }
    fake = mock.MagicMock()
    fake.__enter__.return_value = io.BytesIO(json.dumps(reply).encode())
    with mock.patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
         mock.patch("urllib.request.urlopen", return_value=fake) as op:
        out = tools.search_web("台北 天氣")
    req = op.call_args[0][0]
    assert req.full_url == "https://api.tavily.com/search"
    assert req.get_header("Authorization") == "Bearer test-key"
    sent_headers = {k.lower(): v for k, v in req.headers.items()}
    assert sent_headers["content-type"] == "application/json"
    assert req.method == "POST"
    sent = json.loads(req.data)
    assert sent["query"] == "台北 天氣" and sent["max_results"] == 5
    assert out["source"] == "網路搜尋（Tavily）"
    assert out["answer"] == "台北 10 月 12 日高溫 32 度"
    assert out["results"][0]["title"] == "台北高溫"
    assert out["results"][0]["url"] == "https://example.com/1"
    assert len(out["results"][0]["content"]) <= 300
    assert out["results"][1]["content"] == ""


def test_search_web_declared_and_registered():
    from app import tools
    assert any(d["name"] == "search_web" for d in tools.DECLARATIONS)
    assert "search_web" in tools.FUNCTIONS


def test_time_budget_exhausted_raises_timeout_without_calling_api():
    llm = GeminiLLM(api_key="k", model="main", fallback_models=["lite"], use_tools=False)
    llm.time_budget = 0
    with mock.patch("urllib.request.urlopen") as op:
        try:
            llm([{"role": "user", "content": "hi"}])
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected TimeoutError")
    assert op.call_count == 0


def test_request_timeout_never_exceeds_remaining_budget():
    llm = GeminiLLM(api_key="k", model="main", fallback_models=["lite"], use_tools=False)
    llm.time_budget, llm.timeout = 10, 20
    with mock.patch("urllib.request.urlopen", return_value=_ok("好")) as op:
        assert llm([{"role": "user", "content": "hi"}]) == "好"
    assert op.call_args.kwargs["timeout"] <= 10
