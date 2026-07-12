"""Versioned snapshots + reconnection decision (TSD §3a)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.ingest import SchemaCatalog, SchemaSnapshot
from app.core.snapshots import reconnect_decision, snapshot_age_hours
from app.core.vector_store import InMemoryAdapter

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)


def _snap(age_hours: float) -> SchemaSnapshot:
    return SchemaSnapshot(
        snapshot_id="s",
        project_id="p",
        created_at=NOW - timedelta(hours=age_hours),
        catalog=SchemaCatalog(),
    )


def test_no_snapshot_means_ingest():
    assert reconnect_decision(None, ttl_hours=24, now=NOW) == "ingest"


def test_fresh_snapshot_is_reused():
    assert reconnect_decision(_snap(1), ttl_hours=24, now=NOW) == "reuse"
    assert reconnect_decision(_snap(23.9), ttl_hours=24, now=NOW) == "reuse"


def test_stale_snapshot_triggers_refresh():
    assert reconnect_decision(_snap(25), ttl_hours=24, now=NOW) == "refresh"
    assert reconnect_decision(_snap(24), ttl_hours=24, now=NOW) == "refresh"


def test_snapshot_age():
    assert snapshot_age_hours(_snap(10), now=NOW) == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# Two snapshots coexist in the store and are independently searchable — this is
# what lets the old index keep serving while a new one is built (atomic swap).
# --------------------------------------------------------------------------- #
async def test_snapshots_are_isolated_in_store():
    store = InMemoryAdapter()
    v_old = [[1.0, 0.0]]
    v_new = [[0.0, 1.0]]
    await store.insert_many("p", "old", [{"table": "t", "column": "old_col"}], v_old)
    await store.insert_many("p", "new", [{"table": "t", "column": "new_col"}], v_new)

    old_hit = await store.search("p", "old", [1.0, 0.0], 1)
    new_hit = await store.search("p", "new", [0.0, 1.0], 1)
    assert old_hit[0]["column"] == "old_col"
    assert new_hit[0]["column"] == "new_col"

    # Prune the old snapshot; the new one is unaffected.
    await store.delete_snapshot("p", "old")
    assert await store.search("p", "old", [1.0, 0.0], 1) == []
    assert (await store.search("p", "new", [0.0, 1.0], 1))[0]["column"] == "new_col"
