import logging
from typing import Optional

from app.config import get_settings
from app.core.ingest import SchemaSnapshot, ingest_snapshot
from app.models.schemas import SnapshotInfo
from app.state import ProjectEntry, state

logger = logging.getLogger("linguaql.registry")


def snapshot_info(entry: ProjectEntry, snap: SchemaSnapshot) -> SnapshotInfo:
    return SnapshotInfo(
        snapshot_id=snap.snapshot_id,
        created_at=snap.created_at.isoformat(),
        is_stale=snap.is_stale,
        active=snap.snapshot_id == entry.active_snapshot_id,
        table_count=snap.table_count,
        column_count=snap.column_count,
    )


def sync_project(entry: ProjectEntry) -> None:
    active = entry.snapshots.get(entry.active_snapshot_id or "")
    entry.project.active_snapshot_id = entry.active_snapshot_id
    entry.project.refreshing = entry.refreshing
    if active is not None:
        entry.project.ingested = True
        entry.project.table_count = active.table_count
        entry.project.column_count = active.column_count


async def ingest_and_swap(entry: ProjectEntry) -> SchemaSnapshot:
    """Build a new snapshot, atomically switch the active pointer to it, then
    prune the previously-active snapshot's index. Old snapshot keeps serving
    queries until the switch (TSD §3a safety)."""
    db_url = state.cipher.decrypt_url(entry.enc)
    snap = await ingest_snapshot(
        db_url, entry.project.id, state.embedder, state.store,
        expander=state.expander,
        infer_fks=get_settings().infer_fks,
    )

    old_id = entry.active_snapshot_id
    entry.snapshots[snap.snapshot_id] = snap
    entry.active_snapshot_id = snap.snapshot_id          # <-- atomic switch
    if old_id and old_id != snap.snapshot_id:
        await state.store.delete_snapshot(entry.project.id, old_id)
        entry.snapshots.pop(old_id, None)
    sync_project(entry)
    return snap


async def background_refresh(entry: ProjectEntry) -> None:
    try:
        async with entry.lock:
            await ingest_and_swap(entry)
    except Exception as e:  # noqa: BLE001
        logger.warning("Background snapshot refresh failed: %s", e)
    finally:
        entry.refreshing = False
        sync_project(entry)


def active_snapshot(entry: ProjectEntry) -> Optional[SchemaSnapshot]:
    return entry.snapshots.get(entry.active_snapshot_id or "")
