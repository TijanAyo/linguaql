"""FastAPI entrypoint (TSD §7).

Endpoints:
  GET  /health
  POST /projects                 -> register a source DB
  POST /connect                  -> reconnect-or-create by host hash (TSD §3a)
  POST /projects/{id}/reload     -> build a new immutable schema snapshot
  GET  /projects/{id}/snapshots  -> list this project's snapshots
  POST /projects/{id}/query      -> run the LangGraph pipeline on the active snapshot

The project registry is in-memory for the walking skeleton (durable persistence
is future work). Credentials are Fernet-encrypted at rest (TSD §5). Each ingest
produces a versioned, immutable SchemaSnapshot; the reconnection flow serves a
fresh snapshot instantly, or serves the stale one while a new one is built in the
background and then atomically swapped in (TSD §3a).
"""
# NOTE: no `from __future__ import annotations` here — slowapi wraps the
# rate-limited endpoints, and stringized annotations (PEP 563) can't be resolved
# through the wrapper's module globals, which makes FastAPI misread the request
# body as a query param. Real (non-string) annotations avoid that.

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import copy
from app.agents.graph import run_pipeline
from app.agents.nodes import PipelineContext
from app.config import get_settings
from app.core.embeddings import build_embedder
from app.core.ingest import SchemaSnapshot, ingest_snapshot
from app.core.snapshots import reconnect_decision
from app.core.synonyms import build_expander
from app.core.vector_store import InMemoryAdapter, PgVectorAdapter, VectorStore
from app.utils import db_connections
from app.models.schemas import (
    ConnectRequest,
    ConnectResponse,
    Project,
    ProjectCreate,
    QueryRequest,
    QueryResult,
    SnapshotInfo,
)
from app.utils.crypto import CredentialCipher, EncryptedCredentials

logger = logging.getLogger("linguaql.main")


@dataclass
class ProjectEntry:
    project: Project
    enc: EncryptedCredentials                       # encrypted credentials at rest
    snapshots: dict[str, SchemaSnapshot] = field(default_factory=dict)
    active_snapshot_id: Optional[str] = None
    refreshing: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DailyBudget:
    """Global per-day query counter that guards the funded Anthropic wallet.

    In-memory and single-instance (fine for a $10 demo); the count resets when
    the calendar day rolls over, or on process restart.
    """

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self._day = date.today()
        self.used = 0

    def _rollover(self) -> None:
        today = date.today()
        if today != self._day:
            self._day, self.used = today, 0

    def remaining(self) -> int:
        self._rollover()
        return max(0, self.cap - self.used)

    def try_consume(self) -> bool:
        """Consume one query slot; return False if the day's budget is spent."""
        self._rollover()
        if self.used >= self.cap:
            return False
        self.used += 1
        return True


class AppState:
    embedder = None
    expander = None
    store: VectorStore | None = None
    cipher: CredentialCipher | None = None
    projects: dict[str, ProjectEntry] = {}
    budget: DailyBudget | None = None


state = AppState()


def _client_ip(request: Request) -> str:
    """Real client IP, honoring the PaaS proxy's X-Forwarded-For (first hop)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


_s = get_settings()
RATE_LIMIT = f"{_s.rate_limit_per_minute}/minute;{_s.rate_limit_per_day}/day"
limiter = Limiter(key_func=_client_ip)


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Friendly 429 copy. Per-minute bursts get the 'champ' nudge; the daily
    per-IP ceiling tells them they've had their share for the day."""
    per_min = f"{_s.rate_limit_per_minute} per 1 minute"
    msg = copy.RATE_LIMIT_MINUTE if per_min in str(exc.detail) else copy.RATE_LIMIT_DAY
    return JSONResponse(status_code=429, content={"ok": False, "error": msg})


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    state.budget = DailyBudget(settings.daily_query_cap)
    state.embedder = build_embedder(settings)
    state.expander = build_expander(settings)

    state.cipher, ephemeral = CredentialCipher.from_settings(settings)
    if ephemeral:
        logger.warning(
            "ENCRYPTION_KEY is not set — using an EPHEMERAL Fernet key. Stored "
            "credentials will not survive a restart. Set ENCRYPTION_KEY in production."
        )
    if settings.vector_store == "pgvector":
        try:
            state.store = await PgVectorAdapter.create(
                settings.database_url, state.embedder.dim
            )
        except Exception as e:  # noqa: BLE001 — degrade to in-memory if DB absent
            logger.warning("pgvector unavailable (%s); using in-memory store.", e)
            state.store = InMemoryAdapter()
    else:
        state.store = InMemoryAdapter()
    yield
    if state.store is not None:
        await state.store.close()


app = FastAPI(title="LinguaQL", version="0.2.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# --------------------------------------------------------------------------- #
# Registry helpers
# --------------------------------------------------------------------------- #
def _snapshot_info(entry: ProjectEntry, snap: SchemaSnapshot) -> SnapshotInfo:
    return SnapshotInfo(
        snapshot_id=snap.snapshot_id,
        created_at=snap.created_at.isoformat(),
        is_stale=snap.is_stale,
        active=snap.snapshot_id == entry.active_snapshot_id,
        table_count=snap.table_count,
        column_count=snap.column_count,
    )


def _sync_project(entry: ProjectEntry) -> None:
    active = entry.snapshots.get(entry.active_snapshot_id or "")
    entry.project.active_snapshot_id = entry.active_snapshot_id
    entry.project.refreshing = entry.refreshing
    if active is not None:
        entry.project.ingested = True
        entry.project.table_count = active.table_count
        entry.project.column_count = active.column_count


async def _ingest_and_swap(entry: ProjectEntry) -> SchemaSnapshot:
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
    _sync_project(entry)
    return snap


async def _background_refresh(entry: ProjectEntry) -> None:
    try:
        async with entry.lock:
            await _ingest_and_swap(entry)
    except Exception as e:  # noqa: BLE001
        logger.warning("Background snapshot refresh failed: %s", e)
    finally:
        entry.refreshing = False
        _sync_project(entry)


def _active(entry: ProjectEntry) -> Optional[SchemaSnapshot]:
    return entry.snapshots.get(entry.active_snapshot_id or "")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "embedder": type(state.embedder).__name__ if state.embedder else None,
        "synonyms": type(state.expander).__name__ if state.expander else None,
        "vector_store": type(state.store).__name__ if state.store else None,
        "projects": len(state.projects),
    }


@app.get("/limits")
async def limits() -> dict[str, int]:
    """Remaining shared daily query budget — the frontend counter reads this."""
    budget = state.budget
    if budget is None:
        return {"queries_remaining": 0, "queries_limit": 0}
    return {"queries_remaining": budget.remaining(), "queries_limit": budget.cap}


@app.post("/projects", response_model=Project)
async def create_project(body: ProjectCreate) -> Project:
    pid = uuid.uuid4().hex[:12]
    enc = state.cipher.encrypt(body.db_url)  # plaintext URL is never stored
    project = Project(
        id=pid, name=body.name, db_display=enc.display, db_host_hash=enc.host_hash
    )
    state.projects[pid] = ProjectEntry(project=project, enc=enc)
    return project


@app.get("/projects", response_model=list[Project])
async def list_projects() -> list[Project]:
    return [e.project for e in state.projects.values()]


@app.post("/connect", response_model=ConnectResponse)
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
            snap = await _ingest_and_swap(entry)
        return ConnectResponse(
            project=entry.project, reused=False, refreshing=False,
            active_snapshot=_snapshot_info(entry, snap),
        )

    entry = existing
    decision = reconnect_decision(_active(entry), get_settings().snapshot_ttl_hours)

    if decision == "ingest":
        async with entry.lock:
            snap = await _ingest_and_swap(entry)
        return ConnectResponse(
            project=entry.project, reused=False, refreshing=False,
            active_snapshot=_snapshot_info(entry, snap),
        )

    active = _active(entry)
    if decision == "refresh":
        active.is_stale = True
        if not entry.refreshing:
            entry.refreshing = True
            _sync_project(entry)
            asyncio.create_task(_background_refresh(entry))  # keep serving `active`

    return ConnectResponse(
        project=entry.project, reused=True, refreshing=entry.refreshing,
        active_snapshot=_snapshot_info(entry, active),
    )


@app.post("/projects/{project_id}/reload", response_model=Project)
async def reload_project(project_id: str) -> Project:
    entry = state.projects.get(project_id)
    if entry is None:
        raise HTTPException(404, "Project not found.")
    try:
        async with entry.lock:
            await _ingest_and_swap(entry)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Ingestion failed: {e}")
    return entry.project


@app.get("/projects/{project_id}/snapshots", response_model=list[SnapshotInfo])
async def list_snapshots(project_id: str) -> list[SnapshotInfo]:
    entry = state.projects.get(project_id)
    if entry is None:
        raise HTTPException(404, "Project not found.")
    return [
        _snapshot_info(entry, s)
        for s in sorted(entry.snapshots.values(), key=lambda s: s.created_at, reverse=True)
    ]


@app.post("/projects/{project_id}/query", response_model=QueryResult)
@limiter.limit(RATE_LIMIT)
async def query_project(
    request: Request, project_id: str, body: QueryRequest
) -> QueryResult:
    entry = state.projects.get(project_id)
    if entry is None:
        raise HTTPException(404, "Project not found.")
    active = _active(entry)
    if active is None:
        raise HTTPException(400, "Project not ingested — call /reload first.")

    # Global daily budget — consume a slot only once we're actually going to run
    # the (paid) pipeline, so validation-only rejections above don't cost budget.
    budget = state.budget
    if budget is not None and not budget.try_consume():
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "question": body.question,
                "error": copy.DAILY_CAP,
                "queries_remaining": 0,
                "queries_limit": budget.cap,
            },
        )

    db_url = state.cipher.decrypt_url(entry.enc)
    ctx = PipelineContext(
        settings=get_settings(),
        embedder=state.embedder,
        store=state.store,
        catalog=active.catalog,
        project_id=project_id,
        snapshot_id=active.snapshot_id,
        db_url=db_url,
        dialect=db_connections.dialect_of(db_url),
    )
    result = await run_pipeline(
        ctx, body.question, body.confirmed, body.force_bad_column
    )
    if budget is not None:
        result.queries_remaining = budget.remaining()
        result.queries_limit = budget.cap
    return result
