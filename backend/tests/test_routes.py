"""Route wiring — guards the slowapi/PEP 563 interaction (see routes/query.py)."""
from app.main import app

QUERY_PATH = "/projects/{project_id}/query"


def _route(path: str):
    return next(r for r in app.routes if getattr(r, "path", "") == path)


def test_query_request_is_read_as_a_body():
    """`from __future__ import annotations` in the module holding this endpoint
    makes FastAPI resolve `QueryRequest` against slowapi's globals instead of
    ours. It doesn't raise — it quietly demotes the body to a query param and
    every request 422s. This catches that."""
    route = _route(QUERY_PATH)
    assert "body" in [p.name for p in route.dependant.body_params]
    assert "body" not in [p.name for p in route.dependant.query_params]


def test_expected_routes_are_registered():
    paths = {getattr(r, "path", "") for r in app.routes}
    assert {
        "/health",
        "/limits",
        "/projects",
        "/connect",
        "/projects/{project_id}/reload",
        "/projects/{project_id}/snapshots",
        QUERY_PATH,
    } <= paths
