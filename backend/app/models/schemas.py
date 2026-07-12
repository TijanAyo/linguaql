from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

ChartType = Literal["time_series", "comparison", "stat", "table"]


# LLM-facing structured output
class SQLResponse(BaseModel):
    """The generator's structured answer. Emitted via forced tool-use so the
    shape is guaranteed regardless of model prose."""

    decomposition: str = Field(
        description="Plain-English breakdown of entities, metrics and time filters."
    )
    sql_plan: str = Field(description="Plain-English plan for the query.")
    generated_sql: str = Field(description="The final SQL. Must be a single SELECT.")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Self-rated confidence from 0.0 to 1.0."
    )
    chart_type: ChartType = Field(description="How the result should be visualised.")


# API request/response models
class ProjectCreate(BaseModel):
    name: str
    db_url: str = Field(
        description="Read-only connection URL for the source Postgres DB."
    )


class Project(BaseModel):
    id: str
    name: str
    db_display: str  # redacted connection string (password masked)
    db_host_hash: str  # sha256(host) prefix — no plaintext credentials exposed
    ingested: bool = False
    table_count: int = 0
    column_count: int = 0
    active_snapshot_id: Optional[str] = None
    refreshing: bool = False


class SnapshotInfo(BaseModel):
    snapshot_id: str
    created_at: str
    is_stale: bool
    active: bool
    table_count: int
    column_count: int


class ConnectRequest(BaseModel):
    db_url: str
    name: Optional[str] = None


class ConnectResponse(BaseModel):
    project: Project
    reused: bool  # existing fresh snapshot served as-is
    refreshing: bool  # a background snapshot rebuild is running
    active_snapshot: Optional[SnapshotInfo] = None


class QueryRequest(BaseModel):
    question: str
    # Set true to bypass the Clarifier's low-confidence pause (user confirmed the
    # interpretation / refined the question).
    confirmed: bool = False
    # Escape hatch for the verification step: forces the generator to target a
    # nonexistent column so the validator + self-correction loop can be observed.
    force_bad_column: Optional[str] = None


class QueryResult(BaseModel):
    ok: bool
    question: str
    generated_sql: Optional[str] = None
    chart_type: Optional[ChartType] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    chart_data: dict[str, Any] = Field(default_factory=dict)
    confidence_score: Optional[float] = None
    retry_count: int = 0
    validation_errors: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    needs_reload: bool = False

    # Cost estimator (Node 4)
    complexity_score: Optional[int] = None
    explain_cost: Optional[float] = None

    # Clarifier (Node 5)
    needs_clarification: bool = False
    clarification: Optional[str] = None


# LangGraph state (TSD 4)
class AgentState(TypedDict, total=False):
    project_id: str
    user_question: str

    # retriever output
    retrieved_columns: list[str]
    enriched_tables: list[str]
    schema_context: str
    relationship_context: str

    # generator output
    generated_sql: str
    decomposition: str
    sql_plan: str
    confidence_score: float
    chart_type: ChartType

    # validator / loop
    validation_errors: list[str]
    retry_count: int

    # cost estimator (Node 4)
    complexity_score: int
    explain_cost: float

    # clarifier (Node 5)
    confirmed: bool

    # executor / formatter
    final_result: dict[str, Any]

    # verification hook
    force_bad_column: Optional[str]
