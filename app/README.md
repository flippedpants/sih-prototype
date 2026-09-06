# Zone 1 graph construction and computation

This package contains independently runnable, case-scoped Neo4j analysis jobs. It
has no HTTP API; the later API layer reads the properties and result nodes written
by these jobs.

The placeholder schema lives only in `schema_config.py`. When the real dataset
arrives, update labels, relationship types, and properties there. If entities are
split across labels, update `ENTITY_NODE_LABELS`; query builders already use its
label-union predicate. If transactions become nodes rather than direct
relationships, adapt the two financial query loaders as documented in
`detect_financial_patterns.py`.

Local placeholder workflow:

```bash
docker compose up -d neo4j
docker compose --profile placeholder run --rm placeholder-data
docker compose --profile analysis run --rm validate-scoping
docker compose --profile analysis run --rm project-graphs
docker compose --profile analysis run --rm core-algorithms
docker compose --profile analysis run --rm structural-roles
docker compose --profile analysis run --rm criticality
docker compose --profile analysis run --rm financial-patterns
```

Each analysis command processes every discovered case by default. Most commands
also accept a case ID as their positional argument when run directly:

```bash
NEO4J_URI=bolt://localhost:7687 .venv/bin/python -m app.run_core_algorithms TOY-CASE-01
```

Always run scoping validation first. A blocking warning means algorithm jobs must
not proceed until missing or cross-case data is deliberately resolved.
