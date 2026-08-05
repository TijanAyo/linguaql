# NOTE: do not add `from __future__ import annotations` to this module. The
# endpoint below is wrapped by slowapi's @limiter.limit, and PEP 563 stringized
# annotations get resolved against the *wrapper's* module globals — where
# QueryRequest doesn't exist. FastAPI then silently demotes the body to a query
# param and every request 422s. tests/test_routes.py guards this.

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app import copy
from app.agents.graph import run_pipeline
from app.agents.nodes import PipelineContext
from app.config import get_settings
from app.core.registry import active_snapshot
from app.models.schemas import QueryRequest, QueryResult
from app.ratelimit import RATE_LIMIT, limiter
from app.state import state
from app.utils import db_connections

router = APIRouter(tags=["query"])


@router.post("/projects/{project_id}/query", response_model=QueryResult)
@limiter.limit(RATE_LIMIT)
async def query_project(
    request: Request, project_id: str, body: QueryRequest
) -> QueryResult:
    entry = state.projects.get(project_id)
    if entry is None:
        raise HTTPException(404, "Project not found.")
    active = active_snapshot(entry)
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
