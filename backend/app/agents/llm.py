from __future__ import annotations

from app.config import Settings
from app.models.schemas import SQLResponse

_SQL_TOOL = {
    "name": "emit_sql",
    "description": "Return the final SQL query and its metadata for the user's question.",
    "input_schema": SQLResponse.model_json_schema(),
}

_DIALECT_NAMES = {"postgres": "PostgreSQL", "mysql": "MySQL"}

_SYSTEM_TEMPLATE = """You are a senior analytics engineer that writes SQL for {dialect}.

Rules:
- Output ONLY through the `emit_sql` tool.
- Write a single, read-only SELECT valid for {dialect}. Never DROP/DELETE/UPDATE/INSERT/ALTER.
- Use ONLY the tables and columns provided in the context. Do not invent columns.
- For JOINs, use ONLY the explicit join conditions provided. Do not guess keys.
- Use {dialect}-appropriate functions and identifier quoting for date/time and aggregation.
- Follow the steps: decompose the question, map to columns, plan, then write SQL.
- Classify the best chart type: time_series, comparison, stat, or table.
"""


def _build_user_prompt(
    question: str,
    schema_context: str,
    relationship_context: str,
    validation_errors: list[str],
) -> str:
    parts = [
        "## Available tables and columns",
        schema_context or "(none)",
        "",
        "## Explicit join conditions (use these verbatim; do not guess)",
        relationship_context or "(no foreign-key relationships)",
        "",
        f"## User question\n{question}",
    ]
    if validation_errors:
        parts += [
            "",
            "## Your previous SQL was REJECTED by the validator. Fix these errors:",
            *[f"- {e}" for e in validation_errors],
            "Produce corrected SQL that only uses the listed tables/columns.",
        ]
    return "\n".join(parts)


def generate_sql(
    settings: Settings,
    question: str,
    schema_context: str,
    relationship_context: str,
    validation_errors: list[str],
    dialect: str = "postgres",
) -> SQLResponse:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — the SQL generator requires it."
        )

    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = _build_user_prompt(
        question, schema_context, relationship_context, validation_errors
    )

    msg = client.messages.create(
        model=settings.generator_model,
        max_tokens=1500,
        system=_SYSTEM_TEMPLATE.format(
            dialect=_DIALECT_NAMES.get(dialect, "PostgreSQL")
        ),
        tools=[_SQL_TOOL],
        tool_choice={"type": "tool", "name": "emit_sql"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    for block in msg.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_sql":
            return SQLResponse.model_validate(block.input)

    raise RuntimeError("Generator did not return a structured emit_sql tool call.")
