# Repository Guidelines

## Project Structure & Module Organization

- `app/` contains the FastAPI backend. Keep HTTP wiring in `main.py`, request/response models in `models.py`, and Neo4j persistence and Cypher/GDS retrieval in `neo4j_store.py`.
- `tests/` contains pytest API and integration coverage. Shared fixtures belong in `tests/fixtures.py`; shared client setup belongs in `tests/conftest.py`.
- `docker-compose.yml` starts Neo4j with Graph Data Science (GDS); `Dockerfile` builds the API container.
- Planning and domain context live in the repository Markdown files. Do not put runtime data, credentials, or generated artifacts under source control.

## Build, Test, and Development Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
docker compose up -d neo4j
.venv/bin/python -m pytest -q
docker compose up --build
```

The tests are Neo4j integration tests and require the local Neo4j service. `docker compose up --build` starts both the database and API; the API listens on port `8000`.

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, type hints for public functions, and concise docstrings for module boundaries. Use `snake_case` for functions, variables, and files; use `PascalCase` for Pydantic models and store classes. Keep Cypher parameterized: never interpolate frontend, LLM, dataset, or filter values directly into a query. New domain-specific fields must be represented through dataset metadata and generic attributes, not fixed entity labels or schema migrations.

## Testing Guidelines

Use pytest and name test files `test_*.py` and test functions `test_<behavior>`. Add a failing test before changing API behavior. Cover schema validation, ingest idempotency, Neo4j retrieval, and unsafe-query rejection. Run the complete suite before committing.

## Commit & Pull Request Guidelines

Use concise Conventional-Commit-style subjects, such as `feat: add ...`, `test: cover ...`, `refactor: ...`, or `chore: ...`. Keep commits focused. Pull requests should explain the graph/API impact, list validation commands, link any issue, and include sample request/response payloads for API changes.

## Security & Configuration

Keep `NEO4J_PASSWORD` in environment configuration, never in committed files. The NL layer may submit only the validated query-intent contract; raw Cypher is not an API input.
