from tests.fixtures import FRAUD_SCHEMA


def test_registers_a_dataset_with_custom_entity_and_relation_types(client):
    response = client.post(
        "/api/datasets",
        json={"dataset_id": "fraud-demo", "schema": FRAUD_SCHEMA},
    )

    assert response.status_code == 201, response.text
    assert response.json()["dataset_id"] == "fraud-demo"


def test_returns_registered_schema_without_converting_custom_types_to_fixed_types(client):
    client.post("/api/datasets", json={"dataset_id": "fraud-demo", "schema": FRAUD_SCHEMA})

    response = client.get("/api/datasets/fraud-demo")

    assert response.status_code == 200, response.text
    schema = response.json()["schema"]
    assert {item["name"] for item in schema["entity_types"]} == {"Wallet", "Merchant"}
    assert schema["relation_types"][0]["name"] == "PAYS"


def test_rejects_a_relation_that_references_an_undeclared_entity_type(client):
    invalid_schema = {
        "entity_types": FRAUD_SCHEMA["entity_types"],
        "relation_types": [
            {
                "name": "USES",
                "source_types": ["Wallet"],
                "target_types": ["Phone"],
                "directed": True,
            }
        ],
    }

    response = client.post(
        "/api/datasets", json={"dataset_id": "invalid-demo", "schema": invalid_schema}
    )

    assert response.status_code == 422


def test_rejects_duplicate_schema_type_names(client):
    duplicate_schema = {
        "entity_types": [
            {
                "name": "Wallet",
                "display_field": "wallet_number",
                "identifier_fields": ["wallet_number"],
                "queryable_fields": [],
            },
            {
                "name": "Wallet",
                "display_field": "alternate_number",
                "identifier_fields": ["alternate_number"],
                "queryable_fields": [],
            },
        ],
        "relation_types": [],
    }

    response = client.post(
        "/api/datasets", json={"dataset_id": "duplicate-demo", "schema": duplicate_schema}

    )

    assert response.status_code == 422
