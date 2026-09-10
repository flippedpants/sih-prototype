# Criminal Network Analysis Platform

## Run the application

1. Create the environment file and replace every placeholder secret/password.

```bash
cp .env.example .env
```

Required values in `.env`:

```env
NEO4J_PASSWORD=your-neo4j-password
AUTH_SECRET_KEY=a-long-random-secret
AUTH_BOOTSTRAP_ADMIN_USERNAME=admin
AUTH_BOOTSTRAP_ADMIN_PASSWORD=a-strong-admin-password
```

To enable LLM-generated summaries, also set the API key. If it is omitted, the same batch step stores deterministic template summaries.

```env
OPENROUTER_API_KEY=your-openrouter-api-key
```

2. Build and start the complete application. This one command starts Neo4j,
   ingests the showcase dataset, runs all analysis and summary precomputation,
   then starts the API and frontend.

```bash
docker compose up --build --force-recreate
```

3. Open the application services.

- Frontend: http://localhost:5173
- API documentation: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

4. Run the authenticated smoke test.

```bash
docker compose --profile smoke run --rm smoke-test
```

5. Stop the application.

```bash
docker compose down
```
