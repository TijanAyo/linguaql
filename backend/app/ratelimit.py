from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import copy
from app.config import get_settings


def _client_ip(request: Request) -> str:
    """Real client IP, honoring the PaaS proxy's X-Forwarded-For (first hop)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


_s = get_settings()
RATE_LIMIT = f"{_s.rate_limit_per_minute}/minute;{_s.rate_limit_per_day}/day"
limiter = Limiter(key_func=_client_ip)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Friendly 429 copy. Per-minute bursts get the 'champ' nudge; the daily
    per-IP ceiling tells them they've had their share for the day."""
    per_min = f"{_s.rate_limit_per_minute} per 1 minute"
    msg = copy.RATE_LIMIT_MINUTE if per_min in str(exc.detail) else copy.RATE_LIMIT_DAY
    return JSONResponse(status_code=429, content={"ok": False, "error": msg})
