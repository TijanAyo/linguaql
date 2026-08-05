from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FKEdge:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    confidence: str = "explicit"  # "explicit" | "inferred"

    def join_condition(self) -> str:
        return (
            f"{self.source_table}.{self.source_column} = "
            f"{self.target_table}.{self.target_column}"
        )


@dataclass
class RelationshipGraph:
    edges: list[FKEdge] = field(default_factory=list)
    # undirected adjacency: table -> list[(neighbour, edge)]
    _adj: dict[str, list[tuple[str, FKEdge]]] = field(default_factory=dict)

    def add_edge(self, edge: FKEdge) -> None:
        self.edges.append(edge)
        self._adj.setdefault(edge.source_table, []).append((edge.target_table, edge))
        self._adj.setdefault(edge.target_table, []).append((edge.source_table, edge))

    # -- serialisation --------------------------------------------------- #
    def to_json(self) -> list[dict[str, str]]:
        return [
            {
                "source_table": e.source_table,
                "source_column": e.source_column,
                "target_table": e.target_table,
                "target_column": e.target_column,
                "confidence": e.confidence,
            }
            for e in self.edges
        ]

    @classmethod
    def from_json(cls, data: list[dict[str, str]]) -> "RelationshipGraph":
        g = cls()
        for d in data:
            g.add_edge(
                FKEdge(
                    source_table=d["source_table"],
                    source_column=d["source_column"],
                    target_table=d["target_table"],
                    target_column=d["target_column"],
                    confidence=d.get("confidence", "explicit"),
                )
            )
        return g

    # -- querying -------------------------------------------------------- #
    def _bfs_path(self, start: str, goal: str) -> list[FKEdge]:
        """Shortest edge path between two tables, or [] if disconnected."""
        if start == goal:
            return []
        seen = {start}
        queue: deque[tuple[str, list[FKEdge]]] = deque([(start, [])])
        while queue:
            node, path = queue.popleft()
            for nxt, edge in self._adj.get(node, []):
                if nxt in seen:
                    continue
                new_path = path + [edge]
                if nxt == goal:
                    return new_path
                seen.add(nxt)
                queue.append((nxt, new_path))
        return []

    def neighbors(self, tables: list[str]) -> set[str]:
        """FK-connected tables within 1 hop of any of `tables` (excluding them)."""
        given = set(tables)
        out: set[str] = set()
        for t in given:
            for nbr, _edge in self._adj.get(t, []):
                if nbr not in given:
                    out.add(nbr)
        return out

    def resolve_join_path(self, tables: list[str]) -> str:
        """Return the JOIN conditions connecting `tables`, one per line.

        Greedily connects each table to the growing connected set via the
        shortest BFS path, collecting the join conditions along the way.
        """
        tables = list(dict.fromkeys(tables))  # de-dupe, keep order
        if len(tables) <= 1:
            return ""

        connected = {tables[0]}
        conditions: list[str] = []
        seen_conditions: set[str] = set()

        for target in tables[1:]:
            if target in connected:
                continue
            # find a path from any already-connected table to `target`
            best: list[FKEdge] = []
            for anchor in connected:
                path = self._bfs_path(anchor, target)
                if path and (not best or len(path) < len(best)):
                    best = path
            for edge in best:
                cond = edge.join_condition()
                if cond not in seen_conditions:
                    seen_conditions.add(cond)
                    conditions.append(cond)
                connected.add(edge.source_table)
                connected.add(edge.target_table)
            connected.add(target)

        return "\n".join(conditions)


# Heuristic FK inference  — used when explicit FKs are missing
def _type_family(dtype: str) -> str:
    t = (dtype or "").lower()
    if "int" in t or "serial" in t:
        return "int"
    if "uuid" in t:
        return "uuid"
    if "char" in t or "text" in t:
        return "text"
    return t


def _candidate_tables(base: str, tables: set[str]) -> list[str]:
    """Plausible target tables for a `<base>_id` column (simple pluralisation)."""
    cands = {base, base + "s", base + "es"}
    if base.endswith("y"):
        cands.add(base[:-1] + "ies")
    if base.endswith("s"):
        cands.add(base[:-1])
    # deterministic order, existing tables only
    return [c for c in sorted(cands) if c in tables]


def infer_fk_edges(
    tables: dict[str, list[dict[str, str]]],
    explicit: list[FKEdge],
) -> list[FKEdge]:
    """Infer `{name}_id -> {name}s.id` edges with data-type validation.

    `tables` maps table -> [{"name", "type"}]. Columns already covered by an
    explicit FK are skipped. Inferred edges are tagged confidence="inferred".
    """
    explicit_cols = {(e.source_table, e.source_column) for e in explicit}
    table_names = set(tables)
    coltypes = {t: {c["name"]: c["type"] for c in cols} for t, cols in tables.items()}

    inferred: list[FKEdge] = []
    for table, cols in tables.items():
        for c in cols:
            name = c["name"]
            lname = name.lower()
            if lname == "id" or not lname.endswith("_id"):
                continue
            if (table, name) in explicit_cols:
                continue
            base = lname[:-3]  # strip "_id"
            for target in _candidate_tables(base, table_names):
                if target == table or "id" not in coltypes.get(target, {}):
                    continue
                if _type_family(c["type"]) != _type_family(coltypes[target]["id"]):
                    continue
                inferred.append(
                    FKEdge(table, name, target, "id", confidence="inferred")
                )
                break  # first plausible target wins
    return inferred
