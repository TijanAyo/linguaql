from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    generator_model: str = "claude-opus-4-8"

    # App vector DB
    database_url: str = "postgresql://linguaql:linguaql@localhost:5432/linguaql"
    vector_store: Literal["pgvector", "inmemory"] = "inmemory"

    # Embeddings
    embedder: Literal["hashing", "local", "openai"] = "hashing"
    embed_dim: int = 384
    openai_api_key: str = ""

    # Pipeline
    max_retries: int = 2               # self-correction loop cap (bounds per-query Opus spend)
    retrieve_top_k: int = 15
    source_query_timeout: int = 10

    # for local demos: ENABLE_DEBUG_HOOKS=true.
    enable_debug_hooks: bool = False
    daily_query_cap: int = 100
    rate_limit_per_minute: int = 5
    rate_limit_per_day: int = 10

    complexity_max: int = 50            # static score above which the query is rejected
    explain_timeout: int = 3            # seconds for EXPLAIN
    explain_cost_max: float = 1_000_000.0  # planner Total Cost ceiling

    confidence_threshold: float = 0.7   # below this, halt and ask the user to confirm

    # If empty, an EPHEMERAL key is generated at startup (dev only — credentials
    # won't survive a restart). Generate one: `python -c "from cryptography.fernet
    # import Fernet; print(Fernet.generate_key().decode())"`
    encryption_key: str = ""

    # Schema snapshots / reconnection
    snapshot_ttl_hours: float = 24.0    # snapshots older than this are refreshed

    # Synonym expansion. "none" (default) or "wordnet" (needs nltk).
    synonyms: Literal["none", "wordnet"] = "none"

    # Relationship graph
    infer_fks: bool = True              # heuristic {name}_id -> {name}s.id inference
    enable_join_expansion: bool = True  # 1-hop FK-neighbour expansion in retriever


@lru_cache
def get_settings() -> Settings:
    return Settings()
