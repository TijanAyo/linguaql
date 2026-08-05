from fastapi import APIRouter

from app.state import state

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "embedder": type(state.embedder).__name__ if state.embedder else None,
        "synonyms": type(state.expander).__name__ if state.expander else None,
        "vector_store": type(state.store).__name__ if state.store else None,
        "projects": len(state.projects),
    }


@router.get("/limits")
async def limits() -> dict[str, int]:
    """Remaining shared daily query budget — the frontend counter reads this."""
    budget = state.budget
    if budget is None:
        return {"queries_remaining": 0, "queries_limit": 0}
    return {"queries_remaining": budget.remaining(), "queries_limit": budget.cap}
