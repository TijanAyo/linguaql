import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.core.registry import (
    active_snapshot,
    background_refresh,
    ingest_and_swap,
    snapshot_info,
    sync_project,
)
from app.core.snapshots import reconnect_decision
from app.models.schemas import (
    ConnectRequest,
    ConnectResponse,
    Project,
    ProjectCreate,
    SnapshotInfo,
)
from app.state import ProjectEntry, state

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=Project)
async def create_project(body: ProjectCreate) -> Project:
    pid = uuid.uuid4().hex[:12]
    enc = state.cipher.encrypt(body.db_url)  # plaintext URL is never stored
    project = Project(
        id=pid, name=body.name, db_display=enc.display, db_host_hash=enc.host_hash
    )
    state.projects[pid] = ProjectEntry(project=project, enc=enc)
    return project


@router.get("/projects", response_model=list[Project])
async def list_projects() -> list[Project]:
    return [e.project for e in state.projects.values()]


@router.post("/connect", response_model=ConnectResponse)
async def connect(body: ConnectRequest) -> ConnectResponse:
    """Reconnect by DB-host hash, or create the project if unseen (TSD §3a)."""
    enc = state.cipher.encrypt(body.db_url)
    existing = next(
        (
            e for e in state.projects.values()
            if e.project.db_host_hash == enc.host_hash
            and e.project.db_display == enc.display
        ),
        None,
    )

    if existing is None:
        pid = uuid.uuid4().hex[:12]
        project = Project(
            id=pid, name=body.name or enc.display,
            db_display=enc.display, db_host_hash=enc.host_hash,
        )
        entry = ProjectEntry(project=project, enc=enc)
        state.projects[pid] = entry
        async with entry.lock:
            snap = await ingest_and_swap(entry)
        return ConnectResponse(
            project=entry.project, reused=False, refreshing=False,
            active_snapshot=snapshot_info(entry, snap),
        )

    entry = existing
    decision = reconnect_decision(
        active_snapshot(entry), get_settings().snapshot_ttl_hours
    )

    if decision == "ingest":
        async with entry.lock:
            snap = await ingest_and_swap(entry)
        return ConnectResponse(
            project=entry.project, reused=False, refreshing=False,
            active_snapshot=snapshot_info(entry, snap),
        )

    active = active_snapshot(entry)
    if decision == "refresh":
        active.is_stale = True
        if not entry.refreshing:
            entry.refreshing = True
            sync_project(entry)
            asyncio.create_task(background_refresh(entry))  # keep serving `active`

    return ConnectResponse(
        project=entry.project, reused=True, refreshing=entry.refreshing,
        active_snapshot=snapshot_info(entry, active),
    )


@router.post("/projects/{project_id}/reload", response_model=Project)
async def reload_project(project_id: str) -> Project:
    entry = state.projects.get(project_id)
    if entry is None:
        raise HTTPException(404, "Project not found.")
    try:
        async with entry.lock:
            await ingest_and_swap(entry)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Ingestion failed: {e}")
    return entry.project


@router.get("/projects/{project_id}/snapshots", response_model=list[SnapshotInfo])
async def list_snapshots(project_id: str) -> list[SnapshotInfo]:
    entry = state.projects.get(project_id)
    if entry is None:
        raise HTTPException(404, "Project not found.")
    return [
        snapshot_info(entry, s)
        for s in sorted(entry.snapshots.values(), key=lambda s: s.created_at, reverse=True)
    ]
