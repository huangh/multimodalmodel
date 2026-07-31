"""Tests for hub usage tracking."""

from pathlib import Path

import pytest

from multimodalmodel.hub.usage import UsageStore


@pytest.fixture
def store(tmp_path: Path) -> UsageStore:
    return UsageStore(tmp_path / "usage.db")


def test_record_and_summarize(store: UsageStore):
    store.record("a/plot", user="alice", session_id="s1")
    store.record("a/plot", user="bob", session_id="s2")
    store.record("b/plot", user="alice", session_id="s1")

    summary = store.summary()
    assert [(u.script_id, u.uses) for u in summary] == [("a/plot", 2), ("b/plot", 1)]
    assert summary[0].unique_users == 2
    assert store.counts() == {"a/plot": 2, "b/plot": 1}


def test_repeat_renders_in_one_session_are_deduped(store: UsageStore):
    assert store.record("a/plot", session_id="s1", now=1000.0) is True
    assert store.record("a/plot", session_id="s1", now=1005.0) is False
    assert store.counts() == {"a/plot": 1}


def test_dedupe_is_per_session_and_expires(store: UsageStore):
    store.record("a/plot", session_id="s1", now=1000.0)
    assert store.record("a/plot", session_id="s2", now=1001.0) is True
    assert store.record("a/plot", session_id="s1", now=1000.0 + 31) is True
    assert store.counts() == {"a/plot": 3}


def test_top_limits_and_orders(store: UsageStore):
    for i in range(3):
        store.record("busy", session_id=f"s{i}")
    store.record("quiet", session_id="s9")
    top = store.top(1)
    assert len(top) == 1 and top[0].script_id == "busy" and top[0].uses == 3


def test_since_days_window(store: UsageStore):
    import time

    store.record("old", session_id="s1", now=time.time() - 10 * 86400)
    store.record("new", session_id="s2")
    assert set(store.counts(since_days=1)) == {"new"}
    assert set(store.counts()) == {"old", "new"}


def test_errors_are_counted_but_still_a_use(store: UsageStore):
    store.record("broken", session_id="s1", error="render failed")
    usage = store.summary()[0]
    assert usage.uses == 1 and usage.errors == 1


def test_recent_returns_newest_first(store: UsageStore):
    store.record("first", session_id="s1", now=1000.0)
    store.record("second", session_id="s2", now=2000.0)
    assert [r["script_id"] for r in store.recent()] == ["second", "first"]


def test_store_creates_parent_directory(tmp_path: Path):
    store = UsageStore(tmp_path / "nested" / "dir" / "usage.db")
    store.record("a", session_id="s1")
    assert store.total_events() == 1


def test_separate_connections_see_the_same_data(tmp_path: Path):
    """Kernels are separate processes; each opens its own connection."""
    db = tmp_path / "usage.db"
    UsageStore(db).record("shared", session_id="s1")
    assert UsageStore(db).counts() == {"shared": 1}
