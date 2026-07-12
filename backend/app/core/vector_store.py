from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np


class VectorStore(ABC):
    @abstractmethod
    async def insert_many(
        self,
        project_id: str,
        snapshot_id: str,
        records: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        """Each record is column metadata: {table, column, dtype, sample, doc}."""

    @abstractmethod
    async def search(
        self, project_id: str, snapshot_id: str, query_vector: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        """Return up to top_k column-metadata dicts for one snapshot, by similarity."""

    @abstractmethod
    async def delete_snapshot(self, project_id: str, snapshot_id: str) -> None: ...

    @abstractmethod
    async def delete_project(self, project_id: str) -> None: ...

    async def close(self) -> None:  # optional
        return None


# --------------------------------------------------------------------------- #
# In-memory adapter
# --------------------------------------------------------------------------- #
class InMemoryAdapter(VectorStore):
    def __init__(self) -> None:
        # (project_id, snapshot_id) -> (metas, matrix[n, dim])
        self._store: dict[
            tuple[str, str], tuple[list[dict[str, Any]], Optional[np.ndarray]]
        ] = {}

    async def insert_many(
        self,
        project_id: str,
        snapshot_id: str,
        records: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        mat = np.asarray(vectors, dtype=np.float32) if vectors else None
        self._store[(project_id, snapshot_id)] = (list(records), mat)

    async def search(
        self, project_id: str, snapshot_id: str, query_vector: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        entry = self._store.get((project_id, snapshot_id))
        if not entry or entry[1] is None or len(entry[0]) == 0:
            return []
        metas, mat = entry
        q = np.asarray(query_vector, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn > 0:
            q = q / qn
        scores = mat @ q
        order = np.argsort(-scores)[:top_k]
        return [dict(metas[i], score=float(scores[i])) for i in order]

    async def delete_snapshot(self, project_id: str, snapshot_id: str) -> None:
        self._store.pop((project_id, snapshot_id), None)

    async def delete_project(self, project_id: str) -> None:
        for key in [k for k in self._store if k[0] == project_id]:
            self._store.pop(key, None)


# --------------------------------------------------------------------------- #
# pgvector adapter
# --------------------------------------------------------------------------- #
class PgVectorAdapter(VectorStore):
    def __init__(self, pool: Any, dim: int) -> None:
        self._pool = pool
        self._dim = dim

    @classmethod
    async def create(cls, database_url: str, dim: int) -> "PgVectorAdapter":
        import asyncpg
        from pgvector.asyncpg import register_vector

        async def _init(conn: Any) -> None:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await register_vector(conn)

        pool = await asyncpg.create_pool(
            dsn=_normalise_dsn(database_url), init=_init, min_size=1, max_size=5
        )
        adapter = cls(pool, dim)
        await adapter._ensure_schema()
        return adapter

    async def _ensure_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            # Recreate if the embedding dimension changed OR the snapshot_id
            # column is missing (schema migration for a pre-existing dev table).
            dim_row = await conn.fetchrow(
                "SELECT a.atttypmod AS dim FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relname = 'column_embeddings' AND a.attname = 'embedding';"
            )
            has_snapshot = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'column_embeddings' AND column_name = 'snapshot_id');"
            )
            if dim_row is not None and (
                dim_row["dim"] != self._dim or not has_snapshot
            ):
                await conn.execute("DROP TABLE IF EXISTS column_embeddings;")
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS column_embeddings (
                    id          BIGSERIAL PRIMARY KEY,
                    project_id  TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    tbl         TEXT NOT NULL,
                    col         TEXT NOT NULL,
                    dtype       TEXT,
                    sample      TEXT,
                    doc         TEXT,
                    embedding   vector({self._dim})
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_col_emb_scope "
                "ON column_embeddings (project_id, snapshot_id);"
            )

    async def insert_many(
        self,
        project_id: str,
        snapshot_id: str,
        records: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        rows = [
            (
                project_id,
                snapshot_id,
                r["table"],
                r["column"],
                r.get("dtype"),
                r.get("sample"),
                r.get("doc"),
                np.asarray(v, dtype=np.float32),
            )
            for r, v in zip(records, vectors)
        ]
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO column_embeddings "
                "(project_id, snapshot_id, tbl, col, dtype, sample, doc, embedding) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8);",
                rows,
            )

    async def search(
        self, project_id: str, snapshot_id: str, query_vector: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        q = np.asarray(query_vector, dtype=np.float32)
        async with self._pool.acquire() as conn:
            recs = await conn.fetch(
                "SELECT tbl, col, dtype, sample, doc, "
                "1 - (embedding <=> $3) AS score "
                "FROM column_embeddings "
                "WHERE project_id = $1 AND snapshot_id = $2 "
                "ORDER BY embedding <=> $3 LIMIT $4;",
                project_id,
                snapshot_id,
                q,
                top_k,
            )
        return [
            {
                "table": r["tbl"],
                "column": r["col"],
                "dtype": r["dtype"],
                "sample": r["sample"],
                "doc": r["doc"],
                "score": float(r["score"]),
            }
            for r in recs
        ]

    async def delete_snapshot(self, project_id: str, snapshot_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM column_embeddings "
                "WHERE project_id = $1 AND snapshot_id = $2;",
                project_id,
                snapshot_id,
            )

    async def delete_project(self, project_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM column_embeddings WHERE project_id = $1;", project_id
            )

    async def close(self) -> None:
        await self._pool.close()


def _normalise_dsn(url: str) -> str:
    """asyncpg wants `postgresql://`, not SQLAlchemy-style `postgresql+driver://`."""
    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        url = scheme.split("+", 1)[0] + "://" + rest
    return url
