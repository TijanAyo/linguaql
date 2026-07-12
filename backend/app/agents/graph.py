from __future__ import annotations

from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.nodes import PipelineContext
from app.models.schemas import AgentState, QueryResult

NodeFn = Callable[[AgentState, PipelineContext], Awaitable[dict[str, Any]]]


def _bind(fn: NodeFn, ctx: PipelineContext) -> Callable[[AgentState], Awaitable[dict]]:
    async def _inner(state: AgentState) -> dict[str, Any]:
        return await fn(state, ctx)

    return _inner


def build_graph(ctx: PipelineContext):
    g = StateGraph(AgentState)
    g.add_node("retriever", _bind(nodes.retriever, ctx))
    g.add_node("generator", _bind(nodes.generator, ctx))
    g.add_node("sql_validator", _bind(nodes.sql_validator, ctx))
    g.add_node("increment_retry", _bind(nodes.increment_retry, ctx))
    g.add_node("cost_estimator", _bind(nodes.cost_estimator, ctx))
    g.add_node("cost_reject", _bind(nodes.cost_reject, ctx))
    g.add_node("clarifier", _bind(nodes.clarifier, ctx))
    g.add_node("executor", _bind(nodes.executor, ctx))
    g.add_node("formatter", _bind(nodes.formatter, ctx))

    g.add_edge(START, "retriever")
    g.add_edge("retriever", "generator")
    g.add_edge("generator", "sql_validator")

    retries_left = lambda s: s.get("retry_count", 0) < ctx.settings.max_retries

    # After validation: retry on errors, else move to cost estimation.
    def route_validation(state: AgentState) -> str:
        if state.get("validation_errors"):
            return "increment_retry" if retries_left(state) else "executor"
        return "cost_estimator"

    # After cost estimation: abort (never execute) if EXPLAIN failed; retry on
    # cost feedback; else proceed to the clarifier.
    def route_cost(state: AgentState) -> str:
        if state.get("final_result"):  # EXPLAIN aborted the query
            return "formatter"
        if state.get("validation_errors"):  # too broad / too costly
            return "increment_retry" if retries_left(state) else "cost_reject"
        return "clarifier"

    # After clarifier: halt for confirmation, or execute.
    def route_clarify(state: AgentState) -> str:
        fr = state.get("final_result") or {}
        return "formatter" if fr.get("needs_clarification") else "executor"

    g.add_conditional_edges(
        "sql_validator",
        route_validation,
        {
            "increment_retry": "increment_retry",
            "executor": "executor",
            "cost_estimator": "cost_estimator",
        },
    )
    g.add_conditional_edges(
        "cost_estimator",
        route_cost,
        {
            "formatter": "formatter",
            "increment_retry": "increment_retry",
            "cost_reject": "cost_reject",
            "clarifier": "clarifier",
        },
    )
    g.add_conditional_edges(
        "clarifier",
        route_clarify,
        {"formatter": "formatter", "executor": "executor"},
    )
    g.add_edge("increment_retry", "generator")
    g.add_edge("cost_reject", "formatter")
    g.add_edge("executor", "formatter")
    g.add_edge("formatter", END)

    return g.compile()


async def run_pipeline(
    ctx: PipelineContext,
    question: str,
    confirmed: bool = False,
    force_bad_column: str | None = None,
) -> QueryResult:
    graph = build_graph(ctx)
    init: AgentState = {
        "project_id": ctx.project_id,
        "user_question": question,
        "retry_count": 0,
        "validation_errors": [],
        "confirmed": confirmed,
        "force_bad_column": force_bad_column,
    }
    try:
        final = await graph.ainvoke(init)
    except Exception as e:
        return QueryResult(ok=False, question=question, error=str(e))

    fr: dict[str, Any] = final.get("final_result", {}) or {}
    return QueryResult(
        ok=bool(fr.get("ok")),
        question=question,
        generated_sql=final.get("generated_sql"),
        chart_type=fr.get("chart_type") or final.get("chart_type"),
        columns=fr.get("columns", []),
        rows=fr.get("rows", []),
        chart_data=fr.get("chart_data", {}),
        confidence_score=final.get("confidence_score"),
        retry_count=final.get("retry_count", 0),
        validation_errors=fr.get("validation_errors")
        or final.get("validation_errors", []),
        error=fr.get("error"),
        needs_reload=bool(fr.get("needs_reload")),
        complexity_score=final.get("complexity_score"),
        explain_cost=final.get("explain_cost"),
        needs_clarification=bool(fr.get("needs_clarification")),
        clarification=fr.get("clarification"),
    )
