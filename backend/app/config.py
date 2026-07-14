"""Application configuration (pydantic-settings).

All runtime knobs are read from the environment (see `.env.example`). Only
ANTHROPIC_API_KEY is strictly required for the query pipeline; everything else
has a local-first default so the app runs with zero extra configuration.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Generator LLM (Node 2)
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

    # Public-demo hardening
    # Debug hooks (the "force guardrail" escape hatch) are OFF by default so a
    # hosted deployment can't be driven into the verification path. Turn on only
    # for local demos: ENABLE_DEBUG_HOOKS=true.
    enable_debug_hooks: bool = False
    # Global daily budget: at most this many queries across ALL users per day
    # (protects the funded Anthropic wallet). In-memory; resets on restart.
    daily_query_cap: int = 100
    # Per-IP throttle (slowapi). Burst guard + per-visitor share of the pool.
    rate_limit_per_minute: int = 5
    rate_limit_per_day: int = 10

    # Cost estimator (Node 4)
    complexity_max: int = 50            # static score above which the query is rejected
    explain_timeout: int = 3            # seconds for EXPLAIN
    explain_cost_max: float = 1_000_000.0  # planner Total Cost ceiling

    # Clarifier (Node 5)
    confidence_threshold: float = 0.7   # below this, halt and ask the user to confirm

    # Credential encryption (TSD §5). Fernet master key (url-safe base64, 32 bytes).
    # If empty, an EPHEMERAL key is generated at startup (dev only — credentials
    # won't survive a restart). Generate one: `python -c "from cryptography.fernet
    # import Fernet; print(Fernet.generate_key().decode())"`
    encryption_key: str = ""

    # Schema snapshots / reconnection (TSD §3a)
    snapshot_ttl_hours: float = 24.0    # snapshots older than this are refreshed

    # Synonym expansion (TSD §3d). "none" (default) or "wordnet" (needs nltk).
    synonyms: Literal["none", "wordnet"] = "none"

    # Relationship graph (TSD §3b / §3e)
    infer_fks: bool = True              # heuristic {name}_id -> {name}s.id inference
    enable_join_expansion: bool = True  # 1-hop FK-neighbour expansion in retriever


@lru_cache
def get_settings() -> Settings:
    return Settings()
