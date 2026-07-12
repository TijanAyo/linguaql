"""End-to-end pipeline test over the InMemory vector store.

No Anthropic key and no source DB required: the generator and executor are
stubbed so the graph wiring (retriever → generator → validator → self-correct →
executor → formatter) can be exercised deterministically.
"""
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

PROJECT = "proj_test"
SNAP = "snap_test"


def _catalog() -> SchemaCatalog:
    cat = SchemaCatalog()
    cat.tables = {
        "orders": ["id", "user_id", "product_id", "amount", "created_at"],
        "users": ["id", "name", "country"],
        "products": ["id", "name", "price"],
    }
    cat.column_types = {f"{t}.{c}": "text" for t, cs in cat.tables.items() for c in cs}
    cat.graph.add_edge(FKEdge("orders", "user_id", "users", "id"))
    cat.graph.add_edge(FKEdge("orders", "product_id", "products", "id"))
    return cat


async def _ctx() -> PipelineContext:
    catalog = _catalog()
    embedder = HashingEmbedder(384)
    store = InMemoryAdapter()
    records, docs = [], []
    for t, cols in catalog.tables.items():
        for c in cols:
            records.append({"table": t, "column": c, "dtype": "text", "sample": "", "doc": f"{t} {c}"})
            docs.append(f"{t} {c}")
    await store.insert_many(PROJECT, SNAP, records, embedder.embed(docs))
    return PipelineContext(
        settings=get_settings(),
        embedder=embedder,
        store=store,
        catalog=catalog,
        project_id=PROJECT,
        snapshot_id=SNAP,
        db_url="postgresql://stub",
    )


def _stub_exec(*_a, **_k):
    async def _run(db_url, sql, timeout):
        return (["m", "revenue"], [{"m": "2024-01", "revenue": 370.0}])
    return _run


async def _stub_explain(db_url, sql, timeout):
    return 12.5  # cheap plan, well under the ceiling


async def test_happy_path(monkeypatch):
    def stub_gen(*_a, **_k):
        return SQLResponse(
            decomposition="d", sql_plan="p",
            generated_sql="SELECT created_at AS m, SUM(amount) AS revenue FROM orders GROUP BY 1",
            confidence_score=0.9, chart_type="time_series",
        )

    monkeypatch.setattr(nodes, "generate_sql", stub_gen)
    monkeypatch.setattr(db_connections, "execute_select", _stub_exec())
    monkeypatch.setattr(db_connections, "explain_cost", _stub_explain)

    ctx = await _ctx()
    result = await run_pipeline(ctx, "total revenue by month")

    assert result.ok
    assert result.retry_count == 0
    assert "SUM(amount)" in result.generated_sql
    assert result.chart_type == "time_series"
    assert result.chart_data["y"] == [370.0]


async def test_self_correction_recovers(monkeypatch):
    calls = {"n": 0}

    def stub_gen(settings, question, schema, rels, errors, force=None):
        calls["n"] += 1
        # first attempt: hallucinated column -> validator rejects
        sql = (
            "SELECT bogus_col FROM orders"
            if calls["n"] == 1
            else "SELECT SUM(amount) AS revenue FROM orders"
        )
        return SQLResponse(
            decomposition="d", sql_plan="p", generated_sql=sql,
            confidence_score=0.8, chart_type="stat",
        )

    monkeypatch.setattr(nodes, "generate_sql", stub_gen)
    monkeypatch.setattr(db_connections, "execute_select", _stub_exec())
    monkeypatch.setattr(db_connections, "explain_cost", _stub_explain)

    ctx = await _ctx()
    result = await run_pipeline(ctx, "total revenue")

    assert calls["n"] == 2          # regenerated exactly once
    assert result.retry_count == 1  # self-correction fired
    assert result.ok
    assert "bogus_col" not in (result.generated_sql or "")


async def test_retriever_join_expansion(monkeypatch):
    """Retrieval that only surfaces `orders` still enriches with its FK
    neighbours `users` and `products` (TSD §3e Step 4)."""
    ctx = await _ctx()

    async def only_orders(project_id, snapshot_id, qvec, top_k):
        return [{"table": "orders", "column": "amount"}]

    monkeypatch.setattr(ctx.store, "search", only_orders)
    out = await nodes.retriever({"user_question": "revenue"}, ctx)

    assert set(out["enriched_tables"]) == {"orders", "users", "products"}
    assert "orders.user_id = users.id" in out["relationship_context"]
    assert "orders.product_id = products.id" in out["relationship_context"]


async def test_destructive_never_executes(monkeypatch):
    def stub_gen(*_a, **_k):
        return SQLResponse(
            decomposition="d", sql_plan="p",
            generated_sql="DROP TABLE orders",
            confidence_score=0.9, chart_type="table",
        )

    executed = {"ran": False}

    def bad_exec(*_a, **_k):
        async def _run(*_a, **_k):
            executed["ran"] = True
            return ([], [])
        return _run

    monkeypatch.setattr(nodes, "generate_sql", stub_gen)
    monkeypatch.setattr(db_connections, "execute_select", bad_exec())

    ctx = await _ctx()
    result = await run_pipeline(ctx, "delete everything")

    assert not result.ok
    assert not executed["ran"]       # guardrail prevented execution
    assert result.retry_count == ctx.settings.max_retries
