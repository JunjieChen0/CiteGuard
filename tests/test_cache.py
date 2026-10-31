from citeguard.cache import MISSING, Cache


def test_disk_cache_roundtrip_and_persistence(tmp_path):
    cache = Cache(tmp_path)
    assert cache.get("k") is MISSING
    cache.set("k", {"a": [1, "中文"]})
    assert cache.get("k") == {"a": [1, "中文"]}
    assert Cache(tmp_path).get("k") == {"a": [1, "中文"]}


def test_cache_can_store_none(tmp_path):
    cache = Cache(tmp_path)
    cache.set("404", None)
    assert cache.get("404") is None


def test_cache_expires_after_ttl(tmp_path):
    now = [1000.0]
    cache = Cache(tmp_path, ttl_seconds=10, clock=lambda: now[0])
    cache.set("k", 1)
    now[0] += 11
    assert cache.get("k") is MISSING


def test_memory_cache_when_no_directory():
    cache = Cache(None)
    cache.set("k", 2)
    assert cache.get("k") == 2


def test_corrupted_cache_file_is_ignored(tmp_path):
    cache = Cache(tmp_path)
    cache.set("k", 1)
    for f in tmp_path.glob("*.json"):
        f.write_text("{not json", encoding="utf-8")
    assert cache.get("k") is MISSING
