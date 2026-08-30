# Repository Guidelines

## Project Structure & Module Organization

- `app/main.py` contains FastAPI routes; `app/models.py` holds public API models; `app/neo4j_store.py` owns Neo4j persistence and parameterized Cypher.
- `app/source_ingestion/` is the schema-driven CSV/Excel pipeline: mapping loader, validation, normalized objects, and parser. Add a source by creating `app/source_mappings/<source_type>.json`, not a bespoke parser.
- `app/ingestion-frontend/` is the static upload UI proxied to the API by Nginx.
- `tests/` contains pytest coverage. Place source-ingestion tests in `tests/test_source_ingestion_engine.py`; reuse fixtures in `tests/fixtures.py`.

## Build, Test, and Development Commands

```bash
cp .env.example .env
docker compose up --build
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
docker compose build ingestion-frontend
```

Compose starts Neo4j, the API on `8000`, and the upload UI on `8080`. The complete suite needs Neo4j; parser tests can run without it. Copy `.env.example` and set a non-default password before sharing or deploying the stack.

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, type hints on public functions, and concise module docstrings. Use `snake_case` for modules, functions, and fields; use `PascalCase` for Pydantic models and store classes. Keep Cypher parameterized—never interpolate user, frontend, LLM, dataset, or filter input.

Source mappings must use the controlled entity vocabulary (`PERSON`, `PHONE`, `ACCOUNT`, `VEHICLE`, `ORG`, `LOCATION`) and approved relationship types. Validate mapping changes through the generic engine; do not add source-specific branching. Preserve type-prefixed entity identities and provenance.

## Testing Guidelines

Name tests `test_*.py` and behaviors `test_<outcome>`. Add a failing test before changing API behavior. Cover clean input, structural column failures, per-row validation errors, and mixed mappings. Run focused tests with `pytest -q tests/test_source_ingestion_engine.py`, then the full suite when Neo4j is available.

## Commit & Pull Request Guidelines

Use concise Conventional Commit subjects: `feat: ...`, `test: ...`, `refactor: ...`, or `docs: ...`. Keep commits focused. PRs should state graph/API impact, mapping changes, validation commands, linked issues, and screenshots for frontend changes.

## Security

Do not commit `.env`, source files, credentials, or generated graph data. The future NL layer may submit only validated query intents; raw Cypher is not an API input.
