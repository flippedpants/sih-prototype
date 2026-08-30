from tests.fixtures import FRAUD_RECORD, FRAUD_SCHEMA


def _register_schema(client) -> None:
    response = client.post("/api/datasets", json={"dataset_id": "fraud-demo", "schema": FRAUD_SCHEMA})
    assert response.status_code == 201, response.text


def test_ingests_records_using_dataset_defined_types(client):
    _register_schema(client)

    response = client.post(
        "/api/datasets/fraud-demo/ingestions", json={"records": [FRAUD_RECORD]}
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created_entities"] == 2
    assert result["created_evidence"] == 1
    assert result["created_relations"] == 1
    assert result["skipped_records"] == 0


def test_reimporting_the_same_source_record_is_idempotent(client):
    _register_schema(client)
    payload = {"records": [FRAUD_RECORD]}

    first = client.post("/api/datasets/fraud-demo/ingestions", json=payload)
    second = client.post("/api/datasets/fraud-demo/ingestions", json=payload)

    assert first.status_code == second.status_code == 200
    second_result = second.json()
    assert second_result["created_entities"] == 0
    assert second_result["created_evidence"] == 0
    assert second_result["created_relations"] == 0
    assert second_result["skipped_records"] == 1


def test_rejects_entities_and_relations_not_declared_by_the_dataset_schema(client):
    _register_schema(client)
    bad_record = {
        **FRAUD_RECORD,
        "record_id": "txn-unknown-type",
        "entities": [
            {
                "id": "unknown-1",
                "entity_type": "UnregisteredType",
                "identifiers": {"external_id": "1"},
                "attributes": {},
            }
        ],
        "relations": [],
    }

    response = client.post(
        "/api/datasets/fraud-demo/ingestions", json={"records": [bad_record]}
    )

    assert response.status_code == 422


def test_rejects_a_relation_when_its_endpoints_violate_declared_type_rules(client):
    _register_schema(client)
    bad_record = {
        **FRAUD_RECORD,
        "record_id": "txn-invalid-endpoints",
        "relations": [
            {
                "relation_type": "PAYS",
                "source_ref": "merchant-z",
                "target_ref": "wallet-a",
                "weight": 1,
                "attributes": {"amount": 100},
            }
        ],
    }

    response = client.post(
        "/api/datasets/fraud-demo/ingestions", json={"records": [bad_record]}
    )

    assert response.status_code == 422
