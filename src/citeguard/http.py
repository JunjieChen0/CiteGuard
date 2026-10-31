"""带缓存、按主机限速、429 指数退避的 HTTP 客户端。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from urllib.parse import urlencode, urlsplit

import httpx

from citeguard.cache import MISSING, Cache

USER_AGENT = "CiteGuard/0.1 (academic reference checker; https://github.com/JunjieChen0/CiteGuard)"
_SECRET_PARAMS = {"api_key", "mailto"}
_RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 30.0  # 更长的等待（如 OpenAlex 额度耗尽时的 17 小时）直接放弃

# 第 2 步实测的限流（docs/数据源实测.md）
DEFAULT_MIN_INTERVAL = {
    "api.crossref.org": 0.2,  # DOI 查询 5 次/秒
    "api.crossref.org/search": 1.0,  # 检索 1 次/秒
    "doi.org": 0.2,
    "api.openalex.org": 0.2,
    "api.semanticscholar.org": 1.0,
    "export.arxiv.org": 3.0,
}


class FetchError(RuntimeError):
    """网络失败、限流重试耗尽或非预期的状态码：调用方应判为 UNKNOWN 而不是"不存在"。"""


class HttpClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache: Cache | None = None,
        min_interval: Mapping[str, float] | None = None,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        self._cache = cache if cache is not None else Cache(None)
        self._min_interval = dict(DEFAULT_MIN_INTERVAL if min_interval is None else min_interval)
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._next_slot: dict[str, float] = {}
        self._lock = threading.Lock()
        self._blocked_until: dict[str, float] = {}

    def get_json(self, url: str, params: Mapping[str, str] | None = None,
                 headers: Mapping[str, str] | None = None, rate_key: str | None = None) -> dict | list | None:
        """rate_key：同一主机下需要单独限速的接口（如 Crossref 检索），默认按主机限速。"""
        return self._get(url, params, headers, as_json=True, rate_key=rate_key)

    def get_text(self, url: str, params: Mapping[str, str] | None = None,
                 headers: Mapping[str, str] | None = None, rate_key: str | None = None) -> str | None:
        return self._get(url, params, headers, as_json=False, rate_key=rate_key)

    def _cache_key(self, url: str, params: Mapping[str, str] | None, headers: Mapping[str, str] | None,
                   as_json: bool) -> str:
        public = sorted((k, v) for k, v in (params or {}).items() if k not in _SECRET_PARAMS)
        accept = (headers or {}).get("Accept", "")
        return f"{'json' if as_json else 'text'} {url}?{urlencode(public)} accept={accept}"

    def _wait_turn(self, key: str) -> None:
        # 加锁预约下一个时间槽，锁外睡眠：多线程并发时请求依次排开
        interval = self._min_interval.get(key, 0.0)
        with self._lock:
            now = self._clock()
            last = self._next_slot.get(key)
            slot = now if last is None else max(now, last + interval)
            self._next_slot[key] = slot
        if slot > now:
            self._sleep(slot - now)

    def _get(self, url, params, headers, as_json, rate_key=None):
        key = self._cache_key(url, params, headers, as_json)
        cached = self._cache.get(key)
        if cached is not MISSING:
            return cached
        host = urlsplit(url).hostname or ""
        if self._clock() < self._blocked_until.get(host, 0.0):
            raise FetchError(f"{host} 已因限流暂停使用（服务端要求等待过久）")
        last_error = ""
        for attempt in range(self._max_retries + 1):
            self._wait_turn(rate_key or host)
            try:
                resp = self._client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self._max_retries:
                    self._sleep(2.0 ** attempt)
                continue
            if resp.status_code == 404:
                self._cache.set(key, None)
                return None
            if resp.status_code in _RETRY_STATUS:
                last_error = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else 2.0 ** attempt
                if wait > MAX_RETRY_AFTER_SECONDS:
                    self._blocked_until[host] = self._clock() + wait
                    raise FetchError(f"{url} 返回 HTTP {resp.status_code}，要求等待 {retry_after} 秒，放弃该数据源")
                if attempt < self._max_retries:
                    self._sleep(wait)
                continue
            if resp.status_code >= 400:
                raise FetchError(f"{url} 返回 HTTP {resp.status_code}：{resp.text[:200]}")
            value = resp.json() if as_json else resp.text
            self._cache.set(key, value)
            return value
        raise FetchError(f"{url} 请求失败（重试 {self._max_retries} 次）：{last_error}")
