from fastapi import APIRouter

from app.routes import health, projects, query

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(query.router)

__all__ = ["api_router"]
