from __future__ import annotations

import asyncio
import datetime as _dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import asyncpg

from app.agents.llm import generate_sql
from app.config import Settings
from app.core.embeddings import Embedder
from app.core.ingest import SchemaCatalog
from app.core.vector_store import VectorStore
from app.models.schemas import AgentState
from app.utils import db_connections
from app.utils.sql_parser import complexity_score, validate_sql


@dataclass
class PipelineContext:
    settings: Settings
    embedder: Embedder
    store: VectorStore
    catalog: SchemaCatalog
    project_id: str
    snapshot_id: str
    db_url: str
    dialect: str = "postgres"


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, memoryview)):
        return str(v)
    return v


def _render_schema(catalog: SchemaCatalog, tables: list[str]) -> str:
    lines: list[str] = []
    for t in tables:
        cols = catalog.tables.get(t, [])
        rendered = ", ".join(
            f"{c} {catalog.column_types.get(f'{t}.{c}', '')}".strip() for c in cols
        )
        lines.append(f"{t}({rendered})")
    return "\n".join(lines)


async def retriever(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    question = state["user_question"]
    qvec = ctx.embedder.embed_one(question)
    hits = await ctx.store.search(
        ctx.project_id, ctx.snapshot_id, qvec, ctx.settings.retrieve_top_k
    )

    # parent tables of the retrieved columns, order preserved
    parent_tables = list(dict.fromkeys(h["table"] for h in hits))
    enriched = [t for t in parent_tables if t in ctx.catalog.tables]
    if not enriched:  # cold/empty retrieval -> fall back to whole schema
        enriched = list(ctx.catalog.tables.keys())

    # 1-hop join expansion pull in FK-neighbour tables so the
    # generator has their columns + join paths even if retrieval missed them.
    if ctx.settings.enable_join_expansion:
        for nbr in sorted(ctx.catalog.graph.neighbors(enriched)):
            if nbr in ctx.catalog.tables and nbr not in enriched:
                enriched.append(nbr)

    # table expansion: full column set for each retrieved table
    retrieved_columns = [
        f"{t}.{c}" for t in enriched for c in ctx.catalog.tables.get(t, [])
    ]
    return {
        "retrieved_columns": retrieved_columns,
        "enriched_tables": enriched,
        "schema_context": _render_schema(ctx.catalog, enriched),
        "relationship_context": ctx.catalog.graph.resolve_join_path(enriched),
    }


async def generator(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    retry_count = state.get("retry_count", 0)

    # Verification hook (see QueryRequest.force_bad_column): on the FIRST attempt
    # only, deterministically emit SQL referencing a nonexistent column so the
    # guardrail + self-correction loop can be observed live. A well-aligned model
    # ignores a "please write a bad column" instruction, so we inject it directly.
    force_bad = state.get("force_bad_column")
    if force_bad and retry_count == 0:
        tables = state.get("enriched_tables") or list(ctx.catalog.tables.keys())
        first_table = tables[0] if tables else "orders"
        return {
            "generated_sql": f"SELECT {force_bad} FROM {first_table}",
            "decomposition": "(debug hook)",
            "sql_plan": "(debug hook)",
            "confidence_score": 0.5,
            "chart_type": "table",
        }

    resp = await asyncio.to_thread(
        generate_sql,
        ctx.settings,
        state["user_question"],
        state.get("schema_context", ""),
        state.get("relationship_context", ""),
        state.get("validation_errors", []),
        ctx.dialect,
    )
    return {
        "generated_sql": resp.generated_sql,
        "decomposition": resp.decomposition,
        "sql_plan": resp.sql_plan,
        "confidence_score": resp.confidence_score,
        "chart_type": resp.chart_type,
    }


async def sql_validator(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    errors = validate_sql(
        state.get("generated_sql", ""), ctx.catalog.tables, ctx.dialect
    )
    return {"validation_errors": errors}


async def increment_retry(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    return {"retry_count": state.get("retry_count", 0) + 1}


async def cost_estimator(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    sql = state["generated_sql"]
    score, reasons = complexity_score(sql, ctx.dialect)
    out: dict[str, Any] = {"complexity_score": score}

    if score > ctx.settings.complexity_max:
        out["validation_errors"] = [
            f"Query too broad (complexity {score} > {ctx.settings.complexity_max}): "
            f"{'; '.join(reasons)}. Add filters and/or a LIMIT."
        ]
        return out

    try:
        cost = await db_connections.explain_cost(
            ctx.db_url, sql, ctx.settings.explain_timeout
        )
    except Exception as e:
        return {
            "complexity_score": score,
            "validation_errors": [],
            "final_result": {
                "ok": False,
                "error": f"Unable to estimate query cost ({e}). Please simplify.",
            },
        }

    out["explain_cost"] = cost
    if cost > ctx.settings.explain_cost_max:
        out["validation_errors"] = [
            f"Estimated planner cost {cost:.0f} exceeds the limit "
            f"{ctx.settings.explain_cost_max:.0f}. Add filters or aggregate."
        ]
    else:
        out["validation_errors"] = []
    return out


async def cost_reject(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    return {
        "final_result": {
            "ok": False,
            "error": "Query remained too broad/expensive after "
            f"{state.get('retry_count', 0)} attempts. Add filters or a LIMIT.",
            "validation_errors": state.get("validation_errors", []),
        }
    }


async def clarifier(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    """If generator confidence is low and the user hasn't confirmed, halt BEFORE execution and return the interpretation to confirm."""
    confidence = state.get("confidence_score", 1.0)
    if not state.get("confirmed") and confidence < ctx.settings.confidence_threshold:
        interp = state.get("decomposition", "")
        plan = state.get("sql_plan", "")
        return {
            "final_result": {
                "ok": False,
                "needs_clarification": True,
                "clarification": (
                    f"I'm only {confidence:.0%} confident I understood. "
                    f"My interpretation: {interp} — Plan: {plan}. "
                    "Re-send the query with confirmed=true to run it, or rephrase."
                ),
            }
        }
    return {}


async def executor(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    # Reached with residual errors only when retries are exhausted -> never run it.
    if state.get("validation_errors"):
        return {
            "final_result": {
                "ok": False,
                "error": "SQL failed validation after "
                f"{state.get('retry_count', 0)} self-correction attempts.",
                "validation_errors": state["validation_errors"],
            }
        }

    sql = state["generated_sql"]
    try:
        columns, rows = await db_connections.execute_select(
            ctx.db_url, sql, ctx.settings.source_query_timeout
        )
    except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError) as e:
        return {
            "final_result": {
                "ok": False,
                "error": f"Schema mismatch: {e}",
                "needs_reload": True,
            }
        }
    except Exception as e:  # noqa: BLE001
        return {"final_result": {"ok": False, "error": f"Execution error: {e}"}}

    rows = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
    return {"final_result": {"ok": True, "columns": columns, "rows": rows}}


async def formatter(state: AgentState, ctx: PipelineContext) -> dict[str, Any]:
    result = dict(state.get("final_result", {}))
    if not result.get("ok"):
        return {"final_result": result}

    columns: list[str] = result.get("columns", [])
    rows: list[dict[str, Any]] = result.get("rows", [])
    chart_type = state.get("chart_type", "table")
    chart_data: dict[str, Any] = {}

    try:
        if chart_type in ("time_series", "comparison") and len(columns) >= 2:
            x_col, y_col = columns[0], columns[1]
            chart_data = {
                "x_label": x_col,
                "y_label": y_col,
                "x": [r[x_col] for r in rows],
                "y": [r[y_col] for r in rows],
            }
        elif chart_type == "stat" and columns and rows:
            chart_data = {"label": columns[0], "value": rows[0][columns[0]]}
    except Exception:
        chart_type = "table"
        chart_data = {}

    result["chart_type"] = chart_type
    result["chart_data"] = chart_data
    return {"final_result": result}
