from tests.fixtures import FRAUD_RECORD, FRAUD_SCHEMA


def _prepared_client(client):
    assert client.post("/api/datasets", json={"dataset_id": "fraud-demo", "schema": FRAUD_SCHEMA}).status_code == 201
    assert client.post("/api/datasets/fraud-demo/ingestions", json={"records": [FRAUD_RECORD]}).status_code == 200
    return client


def test_returns_generic_neighbors_without_fixed_entity_labels(client):
    response = _prepared_client(client).post(
        "/api/query", json={"dataset_id": "fraud-demo", "intent": "neighbors", "entity_id": "wallet-a"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["id"] == "merchant-z"


def test_returns_a_connection_path_for_dataset_defined_entities(client):
    response = _prepared_client(client).post(
        "/api/query",
        json={"dataset_id": "fraud-demo", "intent": "connection_path", "source_id": "wallet-a", "target_id": "merchant-z"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"] == ["wallet-a", "merchant-z"]


def test_returns_deterministic_rankings_and_communities(client):
    service = _prepared_client(client)

    ranking = service.post("/api/query", json={"dataset_id": "fraud-demo", "intent": "rank_influencers"})
    communities = service.post("/api/query", json={"dataset_id": "fraud-demo", "intent": "list_communities"})

    assert ranking.status_code == communities.status_code == 200
    assert {row["id"] for row in ranking.json()["results"]} == {"wallet-a", "merchant-z"}
    assert communities.json()["results"] == [["merchant-z", "wallet-a"]]
