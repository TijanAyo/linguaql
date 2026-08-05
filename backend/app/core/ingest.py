import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.embeddings import Embedder
from app.core.relationships import FKEdge, RelationshipGraph, infer_fk_edges
from app.core.synonyms import NullExpander, SynonymExpander
from app.core.vector_store import VectorStore
from app.utils import db_connections


@dataclass
class SchemaCatalog:
    tables: dict[str, list[str]] = field(default_factory=dict)  # table -> columns
    column_types: dict[str, str] = field(default_factory=dict)  # "table.col" -> type
    graph: RelationshipGraph = field(default_factory=RelationshipGraph)

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def column_count(self) -> int:
        return sum(len(c) for c in self.tables.values())

    def all_identifiers(self) -> set[str]:
        idents: set[str] = set(self.tables.keys())
        for table, cols in self.tables.items():
            for col in cols:
                idents.add(col)
                idents.add(f"{table}.{col}")
        return idents


@dataclass
class SchemaSnapshot:
    snapshot_id: str
    project_id: str
    created_at: datetime
    catalog: SchemaCatalog
    is_stale: bool = False

    @property
    def table_count(self) -> int:
        return self.catalog.table_count

    @property
    def column_count(self) -> int:
        return self.catalog.column_count


def _composite_doc(
    table: str, column: str, dtype: str, samples: list[str], synonyms: list[str]
) -> str:
    sample_str = ", ".join(samples) if samples else "n/a"
    syn_str = ", ".join(synonyms) if synonyms else "n/a"
    return (
        f"Table: {table} | Column: {column} | Type: {dtype} "
        f"| Samples: {sample_str} | Synonyms: {syn_str}"
    )


async def ingest_snapshot(
    db_url: str,
    project_id: str,
    embedder: Embedder,
    store: VectorStore,
    snapshot_id: str | None = None,
    expander: SynonymExpander | None = None,
    infer_fks: bool = True,
) -> SchemaSnapshot:
    """Build a NEW immutable snapshot: introspect -> RelationshipGraph -> embed
    -> store the EmbeddingIndex under (project_id, snapshot_id). Existing
    snapshots are left intact so they can keep serving queries during a swap."""
    snapshot_id = snapshot_id or uuid.uuid4().hex[:12]
    expander = expander or NullExpander()
    intro = await db_connections.introspect(db_url)

    catalog = SchemaCatalog()
    for table, cols in intro.tables.items():
        catalog.tables[table] = [c["name"] for c in cols]
        for c in cols:
            catalog.column_types[f"{table}.{c['name']}"] = c["type"]

    # Deterministic relationship graph from explicit FKs.
    for fk in intro.fks:
        catalog.graph.add_edge(
            FKEdge(
                source_table=fk["source_table"],
                source_column=fk["source_column"],
                target_table=fk["target_table"],
                target_column=fk["target_column"],
                confidence="explicit",
            )
        )

    # Heuristic fallback for columns without an explicit FK (TSD §3b).
    if infer_fks:
        for edge in infer_fk_edges(intro.tables, list(catalog.graph.edges)):
            catalog.graph.add_edge(edge)

    # Composite docs + embeddings, one per column.
    records: list[dict[str, str]] = []
    docs: list[str] = []
    for table, cols in intro.tables.items():
        for c in cols:
            dtype = c["type"]
            samples = intro.samples.get((table, c["name"]), [])
            synonyms = expander.expand(c["name"])
            doc = _composite_doc(table, c["name"], dtype, samples, synonyms)
            records.append(
                {
                    "table": table,
                    "column": c["name"],
                    "dtype": dtype,
                    "sample": ", ".join(samples),
                    "doc": doc,
                }
            )
            docs.append(doc)

    vectors = embedder.embed(docs) if docs else []

    await store.delete_snapshot(project_id, snapshot_id)
    if records:
        await store.insert_many(project_id, snapshot_id, records, vectors)

    return SchemaSnapshot(
        snapshot_id=snapshot_id,
        project_id=project_id,
        created_at=datetime.now(timezone.utc),
        catalog=catalog,
    )
