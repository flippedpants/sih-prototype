FRAUD_SCHEMA = {
    "entity_types": [
        {
            "name": "Wallet",
            "display_field": "wallet_number",
            "identifier_fields": ["wallet_number"],
            "queryable_fields": ["provider", "status"],
        },
        {
            "name": "Merchant",
            "display_field": "trade_name",
            "identifier_fields": ["registration_number"],
            "queryable_fields": ["city", "risk_band"],
        },
    ],
    "relation_types": [
        {
            "name": "PAYS",
            "source_types": ["Wallet"],
            "target_types": ["Merchant"],
            "directed": True,
            "weight_field": "amount",
        }
    ],
}


FRAUD_RECORD = {
    "record_id": "txn-0001",
    "entities": [
        {
            "id": "wallet-a",
            "entity_type": "Wallet",
            "identifiers": {"wallet_number": "WALLET-001"},
            "attributes": {"wallet_number": "WALLET-001", "provider": "DemoPay"},
        },
        {
            "id": "merchant-z",
            "entity_type": "Merchant",
            "identifiers": {"registration_number": "REG-900"},
            "attributes": {"trade_name": "Zed Stores", "city": "Delhi"},
        },
    ],
    "relations": [
        {
            "relation_type": "PAYS",
            "source_ref": "wallet-a",
            "target_ref": "merchant-z",
            "weight": 2.5,
            "attributes": {"amount": 2500},
        }
    ],
    "evidence": {
        "source_kind": "transaction_export",
        "occurred_at": "2026-08-01T12:00:00Z",
        "confidence": 0.97,
        "attributes": {"transaction_reference": "TX-100"},
    },
}
