import httpx
import pytest

from citeguard.cache import Cache
from citeguard.http import FetchError, HttpClient


def _client(handler, **kwargs):
    sleeps: list[float] = []
    clock = [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    http = HttpClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        cache=kwargs.pop("cache", Cache(None)),
        sleep=sleep,
        clock=lambda: clock[0],
        **kwargs,
    )
    return http, sleeps


def test_get_json_returns_body_and_none_on_404():
    def handler(request):
        if request.url.path == "/missing":
            return httpx.Response(404, json={"error": "nope"})
        return httpx.Response(200, json={"q": request.url.params["q"]})

    http, _ = _client(handler)
    assert http.get_json("https://api.example.org/x", params={"q": "1"}) == {"q": "1"}
    assert http.get_json("https://api.example.org/missing") is None


def test_retries_on_429_with_backoff_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    http, sleeps = _client(handler)
    assert http.get_json("https://api.example.org/x") == {"ok": True}
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_honours_retry_after_header():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(calls) == 1 else httpx.Response(200, json={})

    http, sleeps = _client(handler)
    http.get_json("https://api.example.org/x")
    assert sleeps == [7.0]


def test_raises_fetch_error_after_exhausting_retries():
    http, _ = _client(lambda request: httpx.Response(503), max_retries=2)
    with pytest.raises(FetchError):
        http.get_json("https://api.example.org/x")


def test_raises_fetch_error_on_transport_error():
    def handler(request):
        raise httpx.ConnectError("down")

    http, _ = _client(handler, max_retries=1)
    with pytest.raises(FetchError):
        http.get_json("https://api.example.org/x")


def test_raises_fetch_error_on_other_client_errors():
    http, _ = _client(lambda request: httpx.Response(403, text="budget exhausted"))
    with pytest.raises(FetchError, match="403"):
        http.get_json("https://api.example.org/x")


def test_rate_limit_spaces_requests_per_host():
    http, sleeps = _client(lambda request: httpx.Response(200, json={}), min_interval={"api.example.org": 1.0})
    http.get_json("https://api.example.org/a")
    http.get_json("https://api.example.org/b")
    http.get_json("https://other.example.org/c")
    assert sleeps == [1.0]


def test_responses_and_404s_are_cached(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(404) if request.url.path == "/gone" else httpx.Response(200, json={"n": 1})

    http, _ = _client(handler, cache=Cache(tmp_path))
    for _ in range(2):
        http.get_json("https://api.example.org/x", params={"a": "1"})
        http.get_json("https://api.example.org/gone")
    assert calls == ["/x", "/gone"]


def test_get_text_returns_raw_text():
    http, _ = _client(lambda request: httpx.Response(200, text="<feed/>"))
    assert http.get_text("https://export.arxiv.org/api/query", params={"id_list": "1"}) == "<feed/>"


def test_cache_key_ignores_secret_params(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={})

    http, _ = _client(handler, cache=Cache(tmp_path))
    http.get_json("https://api.example.org/x", params={"q": "1", "api_key": "secret1"})
    http.get_json("https://api.example.org/x", params={"q": "1", "api_key": "secret2"})
    assert len(seen) == 1
    assert not any("secret" in f.read_text(encoding="utf-8") for f in tmp_path.glob("*.json"))


def test_long_retry_after_fails_fast_and_blocks_host():
    # OpenAlex 额度耗尽时返回 Retry-After: 60709（约 17 小时），不能真的去睡
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(429, headers={"Retry-After": "60709"})

    http, sleeps = _client(handler)
    with pytest.raises(FetchError, match="60709"):
        http.get_json("https://api.openalex.org/works", params={"search": "a"})
    with pytest.raises(FetchError, match="暂停"):
        http.get_json("https://api.openalex.org/works", params={"search": "b"})
    assert calls == ["api.openalex.org"]
    assert sleeps == []
