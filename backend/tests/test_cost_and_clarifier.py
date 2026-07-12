"""Phase 2: Cost Estimator (Node 4) + Clarifier (Node 5)."""
import pytest

from app.agents import nodes
from app.agents.graph import run_pipeline
from app.agents.nodes import PipelineContext
from app.config import get_settings
from app.core.embeddings import HashingEmbedder
from app.core.ingest import SchemaCatalog
from app.core.relationships import FKEdge
from app.core.vector_store import InMemoryAdapter
from app.models.schemas import SQLResponse
from app.utils import db_connections
from app.utils.sql_parser import complexity_score

PROJECT = "proj_cost"
SNAP = "snap_cost"


def _catalog() -> SchemaCatalog:
    cat = SchemaCatalog()
    cat.tables = {
        "orders": ["id", "user_id", "product_id", "amount", "created_at"],
        "users": ["id", "name", "country"],
        "products": ["id", "name", "price"],
    }
    cat.column_types = {f"{t}.{c}": "text" for t, cs in cat.tables.items() for c in cs}
    cat.graph.add_edge(FKEdge("orders", "user_id", "users", "id"))
    return cat


async def _ctx() -> PipelineContext:
    catalog = _catalog()
    emb = HashingEmbedder(384)
    store = InMemoryAdapter()
    recs = [
        {"table": t, "column": c, "dtype": "text", "sample": "", "doc": f"{t} {c}"}
        for t, cs in catalog.tables.items()
        for c in cs
    ]
    await store.insert_many(PROJECT, SNAP, recs, emb.embed([r["doc"] for r in recs]))
    return PipelineContext(
        get_settings(), emb, store, catalog, PROJECT, SNAP, "postgresql://stub"
    )


def _gen(sql: str, confidence: float = 0.9):
    def _stub(*_a, **_k):
        return SQLResponse(
            decomposition="d", sql_plan="p", generated_sql=sql,
            confidence_score=confidence, chart_type="table",
        )
    return _stub


def _tracking_exec():
    ran = {"v": False}

    async def _run(db_url, sql, timeout):
        ran["v"] = True
        return (["x"], [{"x": 1}])

    return ran, _run


# --------------------------------------------------------------------------- #
# ComplexityScorer (static, Layer 1)
# --------------------------------------------------------------------------- #
def test_complexity_penalties():
    # SELECT * (+10) + no WHERE (+20) + no LIMIT (+15) = 45
    score, reasons = complexity_score("SELECT * FROM orders")
    assert score == 45
    assert any("SELECT *" in r for r in reasons)


def test_complexity_clean_query_scores_zero():
    score, _ = complexity_score("SELECT id FROM orders WHERE id = 1 LIMIT 5")
    assert score == 0


def test_complexity_excess_joins():
    sql = (
        "SELECT * FROM orders o1 "
        "JOIN orders o2 ON o1.id = o2.id "
        "JOIN orders o3 ON o1.id = o3.id "
        "JOIN orders o4 ON o1.id = o4.id "
        "JOIN orders o5 ON o1.id = o5.id"
    )
    score, _ = complexity_score(sql)  # 10 + 20 + 15 + (4 joins - 3)*25 = 70
    assert score == 70


# --------------------------------------------------------------------------- #
# Cost Estimator routing (Layer 2 EXPLAIN)
# --------------------------------------------------------------------------- #
async def test_explain_failure_aborts_without_executing(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("planner exploded")

    ran, exec_run = _tracking_exec()
    monkeypatch.setattr(nodes, "generate_sql", _gen("SELECT amount FROM orders WHERE id = 1"))
    monkeypatch.setattr(db_connections, "explain_cost", boom)
    monkeypatch.setattr(db_connections, "execute_select", exec_run)

    result = await run_pipeline(await _ctx(), "some question")

    assert not result.ok
    assert "Unable to estimate query cost" in result.error
    assert not ran["v"]  # TSD safety rule: never execute an unestimable query


async def test_too_broad_rejected_after_retries(monkeypatch):
    broad = (
        "SELECT * FROM orders o1 "
        "JOIN orders o2 ON o1.id = o2.id "
        "JOIN orders o3 ON o1.id = o3.id "
        "JOIN orders o4 ON o1.id = o4.id "
        "JOIN orders o5 ON o1.id = o5.id"
    )
    ran, exec_run = _tracking_exec()
    monkeypatch.setattr(nodes, "generate_sql", _gen(broad))  # always broad
    monkeypatch.setattr(db_connections, "execute_select", exec_run)

    ctx = await _ctx()
    result = await run_pipeline(ctx, "give me everything")

    assert not result.ok
    assert result.complexity_score == 70
    assert result.retry_count == ctx.settings.max_retries
    assert "too broad" in result.error
    assert not ran["v"]


async def test_high_explain_cost_rejected(monkeypatch):
    async def pricey(*_a, **_k):
        return 5_000_000.0  # over the default ceiling

    ran, exec_run = _tracking_exec()
    monkeypatch.setattr(nodes, "generate_sql", _gen("SELECT amount FROM orders WHERE id = 1"))
    monkeypatch.setattr(db_connections, "explain_cost", pricey)
    monkeypatch.setattr(db_connections, "execute_select", exec_run)

    result = await run_pipeline(await _ctx(), "expensive")
    assert not result.ok
    assert not ran["v"]


# --------------------------------------------------------------------------- #
# Clarifier (confidence gate, Node 5)
# --------------------------------------------------------------------------- #
async def test_low_confidence_halts_before_execution(monkeypatch):
    async def cheap(*_a, **_k):
        return 10.0

    ran, exec_run = _tracking_exec()
    monkeypatch.setattr(
        nodes, "generate_sql", _gen("SELECT amount FROM orders WHERE id = 1", confidence=0.4)
    )
    monkeypatch.setattr(db_connections, "explain_cost", cheap)
    monkeypatch.setattr(db_connections, "execute_select", exec_run)

    result = await run_pipeline(await _ctx(), "ambiguous question", confirmed=False)

    assert not result.ok
    assert result.needs_clarification
    assert result.clarification
    assert not ran["v"]


async def test_confirmed_bypasses_clarifier(monkeypatch):
    async def cheap(*_a, **_k):
        return 10.0

    ran, exec_run = _tracking_exec()
    monkeypatch.setattr(
        nodes, "generate_sql", _gen("SELECT amount FROM orders WHERE id = 1", confidence=0.4)
    )
    monkeypatch.setattr(db_connections, "explain_cost", cheap)
    monkeypatch.setattr(db_connections, "execute_select", exec_run)

    result = await run_pipeline(await _ctx(), "ambiguous question", confirmed=True)

    assert result.ok
    assert ran["v"]  # confirmed -> executes
