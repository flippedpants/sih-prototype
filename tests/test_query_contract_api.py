from tests.fixtures import FRAUD_SCHEMA


def _register_schema(client) -> None:
    response = client.post("/api/datasets", json={"dataset_id": "fraud-demo", "schema": FRAUD_SCHEMA})
    assert response.status_code == 201, response.text


def test_accepts_a_supported_typed_query_intent(client):
    _register_schema(client)

    response = client.post(
        "/api/query",
        json={
            "dataset_id": "fraud-demo",
            "intent": "find_entity",
            "entity_type": "Wallet",
            "filters": [{"field": "provider", "operator": "eq", "value": "DemoPay"}],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "find_entity"


def test_rejects_raw_cypher_from_the_frontend_or_llm(client):
    _register_schema(client)

    response = client.post(
        "/api/query",
        json={
            "dataset_id": "fraud-demo",
            "intent": "find_entity",
            "entity_type": "Wallet",
            "cypher": "MATCH (n) DETACH DELETE n",
        },
    )

    assert response.status_code == 422


def test_rejects_mutation_like_text_in_values(client):
    _register_schema(client)

    response = client.post(
        "/api/query",
        json={
            "dataset_id": "fraud-demo",
            "intent": "find_entity",
            "entity_type": "Wallet",
            "filters": [
                {"field": "provider", "operator": "eq", "value": "x') DETACH DELETE n //"}
            ],
        },
    )

    assert response.status_code == 422


def test_rejects_an_unknown_entity_type_or_non_queryable_field(client):
    _register_schema(client)
    unknown_type = client.post(
        "/api/query",
        json={"dataset_id": "fraud-demo", "intent": "find_entity", "entity_type": "Phone"},
    )
    unqueryable_field = client.post(
        "/api/query",
        json={
            "dataset_id": "fraud-demo",
            "intent": "find_entity",
            "entity_type": "Wallet",
            "filters": [{"field": "secret_balance", "operator": "eq", "value": 10}],
        },
    )

    assert unknown_type.status_code == 422
    assert unqueryable_field.status_code == 422


def test_rejects_unsupported_intents(client):
    _register_schema(client)

    response = client.post(
        "/api/query", json={"dataset_id": "fraud-demo", "intent": "run_arbitrary_query"}
    )

    assert response.status_code == 422
