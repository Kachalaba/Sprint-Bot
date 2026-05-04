from __future__ import annotations

import pytest

from services.last_results_cache import LastResultsCache


def test_set_and_get_payload() -> None:
    cache = LastResultsCache(ttl_seconds=10, max_entries=3)
    cache.set((1, 2), {"comment": "hi"})
    payload = cache.get((1, 2))
    assert payload is not None
    assert payload["comment"] == "hi"


def test_get_missing_returns_none() -> None:
    cache = LastResultsCache()
    assert cache.get((1, 2)) is None


def test_payload_isolated_from_caller_mutation() -> None:
    cache = LastResultsCache()
    raw = {"comment": "first"}
    cache.set((1, 2), raw)
    raw["comment"] = "mutated"
    assert cache.get((1, 2))["comment"] == "first"


def test_eviction_when_max_reached() -> None:
    cache = LastResultsCache(ttl_seconds=10, max_entries=2)
    cache.set((1, 1), {"comment": "a"})
    cache.set((1, 2), {"comment": "b"})
    cache.set((1, 3), {"comment": "c"})
    assert cache.get((1, 1)) is None
    assert cache.get((1, 2)) is not None
    assert cache.get((1, 3)) is not None


def test_ttl_expiry() -> None:
    fake_time = [1000.0]
    cache = LastResultsCache(ttl_seconds=10.0, clock=lambda: fake_time[0])
    cache.set((1, 1), {"comment": "a"})

    fake_time[0] += 5
    assert cache.get((1, 1)) is not None

    fake_time[0] += 10
    assert cache.get((1, 1)) is None


def test_update_comment_by_timestamp_updates_all_entries() -> None:
    cache = LastResultsCache()
    cache.set((1, 2), {"timestamp": "T1", "comment": "old"})
    cache.set((3, 4), {"timestamp": "T1", "comment": "old"})
    cache.set((5, 6), {"timestamp": "T2", "comment": "kept"})

    updated = cache.update_comment_by_timestamp("T1", "new")

    assert updated == 2
    assert cache.get((1, 2))["comment"] == "new"
    assert cache.get((3, 4))["comment"] == "new"
    assert cache.get((5, 6))["comment"] == "kept"


def test_discard_removes_entry() -> None:
    cache = LastResultsCache()
    cache.set((1, 2), {"comment": "a"})
    cache.discard((1, 2))
    assert cache.get((1, 2)) is None
    cache.discard((1, 2))


def test_clear_drops_all() -> None:
    cache = LastResultsCache()
    cache.set((1, 1), {"comment": "a"})
    cache.set((1, 2), {"comment": "b"})
    cache.clear()
    assert len(cache) == 0


def test_invalid_ttl_raises() -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        LastResultsCache(ttl_seconds=0)
    with pytest.raises(ValueError, match="max_entries"):
        LastResultsCache(max_entries=0)


def test_invalid_key_raises() -> None:
    cache = LastResultsCache()
    with pytest.raises(ValueError, match="key"):
        cache.set("not-a-tuple", {})  # type: ignore[arg-type]


def test_len_excludes_expired_entries() -> None:
    fake_time = [0.0]
    cache = LastResultsCache(ttl_seconds=5.0, clock=lambda: fake_time[0])
    cache.set((1, 1), {"comment": "a"})
    assert len(cache) == 1
    fake_time[0] = 100.0
    assert len(cache) == 0
