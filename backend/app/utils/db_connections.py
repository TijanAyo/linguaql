import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

import asyncpg


@dataclass
class Introspection:
    tables: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    fks: list[dict[str, str]] = field(default_factory=list)
    samples: dict[tuple[str, str], list[str]] = field(default_factory=dict)


def dialect_of(db_url: str) -> str:
    """Return the sqlglot dialect name: 'mysql' or 'postgres'."""
    base = db_url.split("://", 1)[0].lower().split("+", 1)[0]
    return "mysql" if base in ("mysql", "mariadb") else "postgres"


# Dispatchers
async def introspect(db_url: str) -> Introspection:
    if dialect_of(db_url) == "mysql":
        return await _my_introspect(db_url)
    return await _pg_introspect(db_url)


async def execute_select(
    db_url: str, sql: str, timeout: int
) -> tuple[list[str], list[dict[str, Any]]]:
    if dialect_of(db_url) == "mysql":
        return await _my_execute(db_url, sql, timeout)
    return await _pg_execute(db_url, sql, timeout)


async def explain_cost(db_url: str, sql: str, timeout: int) -> float:
    if dialect_of(db_url) == "mysql":
        return await _my_explain(db_url, sql, timeout)
    return await _pg_explain(db_url, sql, timeout)


# PostgreSQL (asyncpg)
def _pg_dsn(url: str) -> str:
    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        url = scheme.split("+", 1)[0] + "://" + rest
    return url


_PG_COLUMNS_SQL = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
"""

_PG_FK_SQL = """
SELECT tc.table_name AS source_table, kcu.column_name AS source_column,
       ccu.table_name AS target_table, ccu.column_name AS target_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
"""


async def _pg_introspect(db_url: str) -> Introspection:
    conn = await asyncpg.connect(dsn=_pg_dsn(db_url))
    try:
        intro = Introspection()
        for row in await conn.fetch(_PG_COLUMNS_SQL):
            intro.tables.setdefault(row["table_name"], []).append(
                {"name": row["column_name"], "type": row["data_type"]}
            )
        for row in await conn.fetch(_PG_FK_SQL):
            intro.fks.append(dict(row))
        for table, cols in intro.tables.items():
            try:
                sample_rows = await conn.fetch(f'SELECT * FROM "{table}" LIMIT 3;')
            except Exception:
                sample_rows = []
            for col in cols:
                vals = [
                    str(r[col["name"]])
                    for r in sample_rows
                    if r.get(col["name"]) is not None
                ]
                intro.samples[(table, col["name"])] = vals[:3]
        return intro
    finally:
        await conn.close()


async def _pg_execute(
    db_url: str, sql: str, timeout: int
) -> tuple[list[str], list[dict[str, Any]]]:
    conn = await asyncpg.connect(dsn=_pg_dsn(db_url))
    try:
        async with conn.transaction(readonly=True):
            records = await conn.fetch(sql, timeout=timeout)
        columns = list(records[0].keys()) if records else []
        return columns, [dict(r) for r in records]
    finally:
        await conn.close()


async def _pg_explain(db_url: str, sql: str, timeout: int) -> float:
    conn = await asyncpg.connect(dsn=_pg_dsn(db_url))
    try:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {sql}", timeout=timeout)
        payload = rows[0][0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return float(payload[0]["Plan"]["Total Cost"])
    finally:
        await conn.close()


# MySQL (aiomysql)
def _my_params(db_url: str) -> dict[str, Any]:
    p = urlsplit(db_url)
    return {
        "host": p.hostname or "localhost",
        "port": p.port or 3306,
        "user": unquote(p.username) if p.username else None,
        "password": unquote(p.password) if p.password else None,
        "db": p.path.lstrip("/") or None,
    }


async def _my_introspect(db_url: str) -> Introspection:
    import aiomysql

    params = _my_params(db_url)
    conn = await aiomysql.connect(**params)
    try:
        intro = Introspection()
        async with conn.cursor(aiomysql.cursors.DictCursor) as cur:
            await cur.execute(
                "SELECT table_name AS t, column_name AS c, data_type AS d "
                "FROM information_schema.columns WHERE table_schema = %s "
                "ORDER BY table_name, ordinal_position",
                (params["db"],),
            )
            for row in await cur.fetchall():
                intro.tables.setdefault(row["t"], []).append(
                    {"name": row["c"], "type": row["d"]}
                )
            await cur.execute(
                "SELECT table_name AS st, column_name AS sc, "
                "referenced_table_name AS tt, referenced_column_name AS tc "
                "FROM information_schema.key_column_usage "
                "WHERE table_schema = %s AND referenced_table_name IS NOT NULL",
                (params["db"],),
            )
            for row in await cur.fetchall():
                intro.fks.append(
                    {
                        "source_table": row["st"],
                        "source_column": row["sc"],
                        "target_table": row["tt"],
                        "target_column": row["tc"],
                    }
                )
            for table, cols in intro.tables.items():
                try:
                    await cur.execute(f"SELECT * FROM `{table}` LIMIT 3")
                    sample_rows = await cur.fetchall()
                except Exception:
                    sample_rows = []
                for col in cols:
                    vals = [
                        str(r[col["name"]])
                        for r in sample_rows
                        if r.get(col["name"]) is not None
                    ]
                    intro.samples[(table, col["name"])] = vals[:3]
        return intro
    finally:
        conn.close()


async def _my_execute(
    db_url: str, sql: str, timeout: int
) -> tuple[list[str], list[dict[str, Any]]]:
    import aiomysql

    conn = await aiomysql.connect(**_my_params(db_url))
    try:
        async with conn.cursor(aiomysql.cursors.DictCursor) as cur:
            await cur.execute("START TRANSACTION READ ONLY")
            await asyncio.wait_for(cur.execute(sql), timeout=timeout)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = await cur.fetchall()
            await cur.execute("COMMIT")
        return columns, [dict(r) for r in rows]
    finally:
        conn.close()


def _my_explain_cost(payload: dict[str, Any]) -> float:
    """Pull the top-level query_cost from MySQL's EXPLAIN FORMAT=JSON output."""
    cost_info = payload.get("query_block", {}).get("cost_info", {})
    if "query_cost" in cost_info:
        return float(cost_info["query_cost"])
    return 0.0  # EXPLAIN succeeded but reported no cost -> treat as cheap


async def _my_explain(db_url: str, sql: str, timeout: int) -> float:
    import aiomysql

    conn = await aiomysql.connect(**_my_params(db_url))
    try:
        async with conn.cursor() as cur:
            await asyncio.wait_for(
                cur.execute(f"EXPLAIN FORMAT=JSON {sql}"), timeout=timeout
            )
            row = await cur.fetchone()
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return _my_explain_cost(payload)
    finally:
        conn.close()
