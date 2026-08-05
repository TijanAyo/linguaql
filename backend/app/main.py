import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.core.embeddings import build_embedder
from app.core.synonyms import build_expander
from app.core.vector_store import InMemoryAdapter, PgVectorAdapter
from app.ratelimit import limiter, rate_limit_handler
from app.routes import api_router
from app.state import DailyBudget, state
from app.utils.crypto import CredentialCipher

logger = logging.getLogger("linguaql.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    state.budget = DailyBudget(settings.daily_query_cap)
    state.embedder = build_embedder(settings)
    state.expander = build_expander(settings)

    state.cipher, ephemeral = CredentialCipher.from_settings(settings)
    if ephemeral:
        logger.warning(
            "ENCRYPTION_KEY is not set — using an EPHEMERAL Fernet key. Stored "
            "credentials will not survive a restart. Set ENCRYPTION_KEY in production."
        )
    if settings.vector_store == "pgvector":
        try:
            state.store = await PgVectorAdapter.create(
                settings.database_url, state.embedder.dim
            )
        except Exception as e:  # noqa: BLE001 — degrade to in-memory if DB absent
            logger.warning("pgvector unavailable (%s); using in-memory store.", e)
            state.store = InMemoryAdapter()
    else:
        state.store = InMemoryAdapter()
    yield
    if state.store is not None:
        await state.store.close()


app = FastAPI(title="LinguaQL", version="0.2.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(api_router)
