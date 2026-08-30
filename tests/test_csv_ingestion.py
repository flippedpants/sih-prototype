import json

from fastapi.testclient import TestClient

from app.csv_ingestion import parse_csv_uploads
from app.main import create_app
from app.models import DatasetSchemaInput


CSV_MAPPING = {
    "files": [
        {
            "file_name": "payments.csv",
            "record_id_column": "transaction_id",
            "entities": [
                {
                    "id_column": "wallet_id",
                    "entity_type": "Wallet",
                    "display_name_column": "wallet_id",
                    "identifiers": {"wallet_number": "wallet_id"},
                    "attributes": {"provider": "provider"},
                },
                {
                    "id_column": "merchant_id",
                    "entity_type": "Merchant",
                    "display_name_column": "merchant_name",
                    "identifiers": {"registration_number": "merchant_id"},
                    "attributes": {"city": "city"},
                },
            ],
            "relations": [
                {
                    "relation_type": "PAYS",
                    "source_id_column": "wallet_id",
                    "target_id_column": "merchant_id",
                    "weight_column": "amount",
                    "attributes": {"amount": "amount"},
                }
            ],
            "evidence": {
                "source_kind": "payments_export",
                "confidence_column": "confidence",
                "attributes": {"source_reference": "transaction_id"},
            },
        }
    ]
}


class FakeGraphStore:
    def __init__(self) -> None:
        self.schema = DatasetSchemaInput(
            dataset_id="fraud-demo",
            entity_types=[{"name": "Wallet"}, {"name": "Merchant"}],
            relation_types=[{"name": "PAYS", "source_types": ["Wallet"], "target_types": ["Merchant"]}],
        )
        self.evidence_ids: set[str] = set()
        self.ingested = []

    def get_dataset(self, dataset_id):
        if dataset_id != "fraud-demo":
            raise KeyError(dataset_id)
        return type("Dataset", (), {"schema": self.schema})()

    def evidence_exists(self, dataset_id, evidence_id):
        return evidence_id in self.evidence_ids

    def entity_types(self, dataset_id, entity_ids):
        return {}

    def ingest(self, dataset_id, entities, evidence, relations):
        self.ingested.append((entities, evidence, relations))
        self.evidence_ids.update(item.id for item in evidence)
        return {"entities": len(entities), "evidence": len(evidence), "relations": len(relations)}


def test_parses_multiple_uploaded_files_using_their_own_mappings():
    mapping = {
        "files": CSV_MAPPING["files"]
        + [
            {
                "file_name": "wallets.csv",
                "record_id_column": "export_id",
                "entities": [
                    {
                        "id_column": "wallet_id",
                        "entity_type": "Wallet",
                        "attributes": {"status": "status"},
                    }
                ],
                "evidence": {"source_kind": "wallet_export"},
            }
        ]
    }
    records = parse_csv_uploads(
        [
            ("payments.csv", b"transaction_id,wallet_id,merchant_id,merchant_name,provider,city,amount,confidence\ntxn-1,w-1,m-1,Acme,DemoPay,Delhi,2500,0.9\n"),
            ("wallets.csv", b"export_id,wallet_id,status\nwallet-1,w-1,active\n"),
        ],
        mapping,
    )

    assert len(records) == 2
    payment, wallet = records
    assert payment.record_id == "payments.csv:txn-1"
    assert payment.entities[0].id == wallet.entities[0].id == "w-1"
    assert payment.entities[1].attributes == {"city": "Delhi"}
    assert payment.relations[0].weight == 2500.0
    assert payment.evidence["confidence"] == 0.9
    assert wallet.evidence["source_kind"] == "wallet_export"


def test_csv_endpoint_ingests_multipart_file_into_the_graph_store():
    store = FakeGraphStore()
    with TestClient(create_app(graph_store=store)) as client:
        response = client.post(
            "/api/datasets/fraud-demo/ingestions/csv",
            files=[("files", ("payments.csv", b"transaction_id,wallet_id,merchant_id,merchant_name,provider,city,amount,confidence\ntxn-1,w-1,m-1,Acme,DemoPay,Delhi,2500,0.9\n", "text/csv"))],
            data={"mapping": json.dumps(CSV_MAPPING)},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"created_entities": 2, "created_evidence": 1, "created_relations": 1, "skipped_records": 0, "processed_files": 1}
    assert store.ingested[0][2][0].source_id == "w-1"


def test_csv_endpoint_rejects_an_uploaded_file_without_a_mapping():
    with TestClient(create_app(graph_store=FakeGraphStore())) as client:
        response = client.post(
            "/api/datasets/fraud-demo/ingestions/csv",
            files=[("files", ("unknown.csv", b"id\n1\n", "text/csv"))],
            data={"mapping": json.dumps(CSV_MAPPING)},
        )

    assert response.status_code == 422
    assert "no mapping" in response.json()["detail"]
