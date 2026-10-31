"""本地 JSON 缓存：同一请求不重复访问数据源（避免限流，也让实验可复现）。"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

MISSING: Any = object()
DEFAULT_TTL_SECONDS = 30 * 24 * 3600


class Cache:
    def __init__(
        self,
        directory: Path | None,
        ttl_seconds: float | None = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.directory = Path(directory) if directory is not None else None
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._memory: dict[str, tuple[float, Any]] = {}
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        assert self.directory is not None
        return self.directory / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]}.json"

    def get(self, key: str) -> Any:
        if self.directory is None:
            entry = self._memory.get(key)
        else:
            try:
                data = json.loads(self._path(key).read_text(encoding="utf-8"))
                entry = (data["created"], data["value"])
            except (OSError, ValueError, KeyError):
                entry = None
        if entry is None:
            return MISSING
        created, value = entry
        if self.ttl_seconds is not None and self._clock() - created > self.ttl_seconds:
            return MISSING
        return value

    def set(self, key: str, value: Any) -> None:
        created = self._clock()
        if self.directory is None:
            self._memory[key] = (created, value)
            return
        payload = {"key": key, "created": created, "value": value}
        self._path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
