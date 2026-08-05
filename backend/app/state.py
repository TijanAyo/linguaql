import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.core.ingest import SchemaSnapshot
from app.core.vector_store import VectorStore
from app.models.schemas import Project
from app.utils.crypto import CredentialCipher, EncryptedCredentials


@dataclass
class ProjectEntry:
    project: Project
    enc: EncryptedCredentials                       # encrypted credentials at rest
    snapshots: dict[str, SchemaSnapshot] = field(default_factory=dict)
    active_snapshot_id: Optional[str] = None
    refreshing: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DailyBudget:
    def __init__(self, cap: int) -> None:
        self.cap = cap
        self._day = date.today()
        self.used = 0

    def _rollover(self) -> None:
        today = date.today()
        if today != self._day:
            self._day, self.used = today, 0

    def remaining(self) -> int:
        self._rollover()
        return max(0, self.cap - self.used)

    def try_consume(self) -> bool:
        """Consume one query slot; return False if the day's budget is spent."""
        self._rollover()
        if self.used >= self.cap:
            return False
        self.used += 1
        return True


class AppState:
    embedder = None
    expander = None
    store: VectorStore | None = None
    cipher: CredentialCipher | None = None
    projects: dict[str, ProjectEntry] = {}
    budget: DailyBudget | None = None


state = AppState()
