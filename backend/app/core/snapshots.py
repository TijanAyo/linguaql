from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from app.core.ingest import SchemaSnapshot

Decision = Literal["ingest", "reuse", "refresh"]


def snapshot_age_hours(
    snapshot: SchemaSnapshot, now: Optional[datetime] = None
) -> float:
    now = now or datetime.now(timezone.utc)
    return (now - snapshot.created_at).total_seconds() / 3600.0


def reconnect_decision(
    active: Optional[SchemaSnapshot],
    ttl_hours: float,
    now: Optional[datetime] = None,
) -> Decision:
    if active is None:
        return "ingest"
    if snapshot_age_hours(active, now) < ttl_hours:
        return "reuse"
    return "refresh"
