# LinguaQL

Ask a read-only PostgreSQL or MySQL database questions in plain English and get
accurate SQL, results, and an auto-generated chart — with deterministic
guardrails and a self-correcting query engine.

This repository implements the **full TSD v3.0 query engine** — all seven
LangGraph nodes (retriever, generator, validator, cost estimator, clarifier,
executor, formatter) with self-correction — plus ingestion. Remaining TSD
modules (synonyms, MySQL, observability, eval CI) are deferred; see `Roadmap`
below.

## Architecture

```
Ingestion:  connect → read information_schema (+ FKs) → RelationshipGraph
            → composite column docs → embed → VectorStore (pgvector)

Query:  [retriever] → [generator: Claude Opus 4.8] → [sql_validator: sqlglot]
             ▲                                              │
             │  self-correction (max 3;                     │
             └── validation OR cost feedback) ──────────────┤
             │                                              │
             └── [cost_estimator: complexity + EXPLAIN] ────┤
                     (EXPLAIN fails ⇒ abort, never execute)  │
              → [clarifier: confidence gate] → [executor] → [formatter] → result + chart
                     (confidence < 0.7 ⇒ halt & ask to confirm)
```

- **Generator LLM:** Claude Opus 4.8 (`claude-opus-4-8`) via the official
  `anthropic` SDK, forced tool-use for a guaranteed `SQLResponse` shape.
- **Embeddings:** pluggable. `EMBEDDER=hashing` (default) is a zero-dependency
  `HashingEmbedder` (no keys, no downloads); `EMBEDDER=openai` uses
  `text-embedding-3-small` (bundled, needs `OPENAI_API_KEY`, `EMBED_DIM=1536`);
  `EMBEDDER=local` uses `all-MiniLM-L6-v2` (`pip install sentence-transformers`).
  On a bad config the factory logs a warning and falls back to hashing.
- **Deterministic synonyms** (`SYNONYMS=wordnet`) — column names are tokenized
  and expanded via WordNet (non-LLM, reproducible) to enrich the embedding docs
  (`amount → sum, quantity`; `price → cost, monetary value`), improving recall.
- **Guardrails:** `sqlglot` rejects any non-`SELECT` / destructive statement and
  cross-checks every identifier against the ingested schema.
- **Cost control:** a static complexity score (SELECT * / no WHERE / no LIMIT /
  excess JOINs) plus a real `EXPLAIN` estimate gate the query; anything
  unestimable is rejected, never executed.
- **Clarifier:** if the generator's confidence is below 0.7 the pipeline halts
  and returns its interpretation for you to confirm (`confirmed: true`) or refine.
- **Joins are 100% deterministic** — the LLM is handed explicit `a.col = b.col`
  conditions from the FK graph, never asked to guess. Missing FKs are recovered
  by heuristic inference (`{name}_id → {name}s.id`, type-validated,
  `confidence: "inferred"`), and retrieval does 1-hop join expansion so a query
  that surfaces one table also gets its FK neighbours' columns + join paths.
- **Credentials encrypted at rest** — source-DB URLs are split into parts and
  each is Fernet-encrypted (master key from `ENCRYPTION_KEY`); API responses show
  only a redacted `db_display` (password masked), never plaintext.
- **Versioned schema snapshots + reconnection** — every ingest builds an
  immutable, `snapshot_id`-tagged index. `POST /connect` reconnects by DB-host
  hash: a snapshot younger than `SNAPSHOT_TTL_HOURS` (24h) is served instantly;
  a stale one keeps serving while a fresh snapshot is built in the background and
  **atomically swapped** in (old index pruned).

## Run it (Docker — recommended)

```bash
cp .env.example .env
# put your key in .env:  ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
```

Then open **http://localhost:3000**, click **Connect & Ingest** (the sample DB
URL is prefilled), and ask e.g. *"total revenue by month"*.

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000  (`/health`, `/docs`)
- Sample source DB (seeded e-commerce schema): `sample-db` service
- App vector DB (pgvector): `app-postgres` service

The backend connects to the sample DB at
`postgresql://demo:demo@sample-db:5432/shop` (the value prefilled in the UI).

**Try MySQL too:** start the optional seeded MySQL service and connect it in the UI:

```bash
docker compose --profile mysql up -d sample-mysql
# then in the UI use:  mysql://root:root@sample-mysql:3306/shop
```

The engine auto-detects the dialect from the URL scheme and generates
MySQL-appropriate SQL (e.g. `DATE_FORMAT` instead of `date_trunc`).


## Run the backend locally (no Docker)

Each contributor creates their own virtualenv from the pinned `requirements.txt`
(the venv itself is git-ignored — `requirements.txt` is the reproducibility
contract):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export VECTOR_STORE=inmemory          # no app DB needed
uvicorn app.main:app --reload
```

## Tests

```bash
cd backend && source .venv/bin/activate
pip install -r requirements.txt
pytest                                
```
