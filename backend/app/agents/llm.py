from __future__ import annotations

import logging

from app import copy
from app.config import Settings
from app.models.schemas import SQLResponse

logger = logging.getLogger("linguaql.generator")


class GeneratorError(RuntimeError):
    """A generator failure with a user-safe message.

    `user_message` is friendly, sanitized copy shown to the visitor; `detail`
    is the raw cause, logged server-side but never returned in the API response
    (so we don't leak SDK internals like "your credit balance is too low").
    """

    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def _friendly_anthropic_error(exc: Exception) -> str:
    """Map an Anthropic SDK exception to sanitized, on-brand copy."""
    import anthropic

    text = str(getattr(exc, "message", "") or exc).lower()
    if isinstance(exc, anthropic.RateLimitError):
        return copy.UPSTREAM_BUSY
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return copy.CONFIG_ISSUE
    if "credit" in text or "billing" in text or "balance" in text:
        return copy.BUDGET_EXHAUSTED
    if isinstance(exc, anthropic.APIConnectionError):
        return copy.UPSTREAM_BUSY
    return copy.GENERIC

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
        raise GeneratorError(
            copy.NO_KEY,
            detail="ANTHROPIC_API_KEY is not set — the SQL generator requires it.",
        )

    import anthropic
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = _build_user_prompt(
        question, schema_context, relationship_context, validation_errors
    )

    try:
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
    except anthropic.APIError as e:  # credit exhaustion, rate limit, auth, network…
        logger.warning("Anthropic call failed: %s", e)
        raise GeneratorError(_friendly_anthropic_error(e), detail=str(e)) from e

    for block in msg.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_sql":
            return SQLResponse.model_validate(block.input)

    raise GeneratorError(
        copy.GENERIC,
        detail="Generator did not return a structured emit_sql tool call.",
    )
