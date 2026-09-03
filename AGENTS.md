# Repository Guidelines

## Project Structure

- `app/main.py` defines FastAPI routes; `app/models.py` contains public API contracts; `app/neo4j_store.py` owns production Neo4j persistence and parameterized Cypher.
- `app/source_ingestion/` is the production CSV/Excel pipeline. It loads mappings, resolves explicit column aliases, validates rows, and produces normalized entities and relationships.
- Add a production source with `app/source_mappings/<source_type>.json`; do not add a parser branch for a particular file type.
- `app/ingestion-frontend/` is the Nginx-served upload UI. Tests are under `tests/`.
- `demo_run/` is intentionally separate. It imports the bundled synthetic case with direct Neo4j edges for visualization; it does not change the production graph model.

## Run and Test

```bash
cp .env.example .env
docker compose up --build
docker compose --profile demo run --rm demo-run
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Compose exposes Neo4j Browser on `7474`, the API on `8000`, and the upload UI on `8080`. The demo must run through Docker because `.env` uses the Compose hostname `bolt://neo4j:7687`. Focus parser tests with `pytest -q tests/test_source_ingestion_engine.py`; run demo tests with `pytest -q tests/test_demo_run.py`.

## Design and Style

Use Python 3.12, four-space indentation, type hints on public functions, `snake_case` names, and `PascalCase` models/classes. Never interpolate user, frontend, LLM, dataset, or filter values into Cypher.

Production mappings use the controlled entity vocabulary: `PERSON`, `PHONE`, `ACCOUNT`, `VEHICLE`, `ORG`, `LOCATION`. They must use explicit column aliases, preserve type-prefixed identities and provenance, and reject unknown meaning rather than guessing. The production store retains first-class `:Relation` nodes; only the demo creates direct `:CALLED`, `:TRANSACTED`, and `:MENTIONED_IN_FIR` edges.

## Tests, Commits, and Security

Add a failing test before changing API behavior. Cover clean input, structural failures, row errors, alias resolution, and mixed mappings. Use focused Conventional Commit subjects such as `feat: ...` or `test: ...`. PRs should describe graph/API impact and validation commands. Never commit `.env`, credentials, source datasets, or generated graph data; raw Cypher is not an NL/API input.
