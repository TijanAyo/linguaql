from __future__ import annotations

import sqlglot
from sqlglot import exp

_DESTRUCTIVE = (
    exp.Drop,
    exp.Delete,
    exp.Update,
    exp.Insert,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Command,  # e.g. bare GRANT/SET/etc. that sqlglot maps to Command
)


def validate_sql(
    sql: str, catalog_tables: dict[str, list[str]], dialect: str = "postgres"
) -> list[str]:
    errors: list[str] = []

    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return ["Empty SQL."]

    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as e:  # noqa: BLE001
        return [f"Could not parse SQL: {e}"]

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return ["Only a single SQL statement is allowed."]

    root = statements[0]

    # 1) destructive / non-SELECT rejection
    for node in root.walk():
        if isinstance(node, _DESTRUCTIVE):
            return [
                f"Rejected: only read-only SELECT queries are allowed "
                f"(found {type(node).__name__.upper()})."
            ]

    # The top-level must resolve to a SELECT (allow leading CTEs / parens).
    select = root.find(exp.Select)
    if select is None:
        return ["Rejected: query is not a SELECT."]

    # 2) identifier cross-reference
    allowed_tables = {t.lower() for t in catalog_tables}
    allowed_columns = {c.lower() for cols in catalog_tables.values() for c in cols}

    # CTE names and aliases are legitimate identifiers too.
    cte_names = {c.alias_or_name.lower() for c in root.find_all(exp.CTE)}
    alias_names = {a.alias.lower() for a in root.find_all(exp.Alias) if a.alias}
    table_aliases = {t.alias.lower() for t in root.find_all(exp.Table) if t.alias}

    known_tables = allowed_tables | cte_names
    known_column_names = allowed_columns | alias_names | cte_names

    for table in root.find_all(exp.Table):
        name = table.name.lower()
        if name not in known_tables:
            errors.append(f"Unknown table: '{table.name}'.")

    for column in root.find_all(exp.Column):
        name = column.name.lower()
        if name == "*" or not name:
            continue
        qualifier = (column.table or "").lower()
        # qualifier may be a real table or a table alias
        if qualifier and qualifier not in (allowed_tables | table_aliases | cte_names):
            errors.append(f"Unknown table qualifier: '{column.table}'.")
        if name not in known_column_names:
            errors.append(f"Unknown column: '{column.name}'.")

    # de-dupe while preserving order
    seen: set[str] = set()
    deduped = [e for e in errors if not (e in seen or seen.add(e))]
    return deduped


def complexity_score(sql: str, dialect: str = "postgres") -> tuple[int, list[str]]:
    """Static cost heuristic (TSD §4 Node 4, Layer 1). Returns (score, reasons).

    Penalties: SELECT * (+10), no WHERE (+20), no LIMIT (+15),
    each JOIN beyond the 3rd (+25).
    """
    try:
        root = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001 — validator already parsed it; be safe anyway
        return 0, []

    score = 0
    reasons: list[str] = []

    is_star = any(
        isinstance(e, exp.Star)
        for sel in root.find_all(exp.Select)
        for e in sel.expressions
    )
    if is_star:
        score += 10
        reasons.append("uses SELECT * (+10)")

    if root.find(exp.Where) is None:
        score += 20
        reasons.append("no WHERE filter (+20)")

    if root.find(exp.Limit) is None:
        score += 15
        reasons.append("no LIMIT (+15)")

    join_count = len(list(root.find_all(exp.Join)))
    if join_count > 3:
        extra = (join_count - 3) * 25
        score += extra
        reasons.append(f"{join_count} JOINs (+{extra})")

    return score, reasons
