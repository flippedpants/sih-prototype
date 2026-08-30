"""FastAPI entry point for the metadata-driven graph backend."""
from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status

from .models import DatasetRegistration, DatasetSchemaInput, EvidenceInput, QueryIntent, RecordsIngestionRequest, RelationInput
from .store import MemoryGraphStore
from .neo4j_store import Neo4jGraphStore


def create_app() -> FastAPI:
    application = FastAPI(title="Graph Intelligence API", version="0.1.0")
    if os.getenv("GRAPH_STORE", "memory").lower() == "neo4j":
        application.state.graph_service = Neo4jGraphStore(os.environ["NEO4J_URI"], os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    else:
        application.state.graph_service = MemoryGraphStore()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "store": os.getenv("GRAPH_STORE", "memory")}

    @application.post("/api/datasets", status_code=status.HTTP_201_CREATED)
    def register_dataset(request: DatasetRegistration, store: MemoryGraphStore = Depends(get_graph_service)) -> dict[str, Any]:
        try:
            schema = DatasetSchemaInput(dataset_id=request.dataset_id, **request.schema)
            registered = store.register_dataset(schema)
            return {"dataset_id": request.dataset_id, "schema": _public_schema(registered)}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/datasets/{dataset_id}")
    def get_dataset(dataset_id: str, store: MemoryGraphStore = Depends(get_graph_service)) -> dict[str, Any]:
        try:
            return {"dataset_id": dataset_id, "schema": _public_schema(store.schema_dict(store.get_dataset(dataset_id)))}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset not found") from error

    @application.post("/api/datasets/{dataset_id}/ingestions")
    def ingest_records(dataset_id: str, request: RecordsIngestionRequest, store: MemoryGraphStore = Depends(get_graph_service)) -> dict[str, int]:
        created = {"created_entities": 0, "created_evidence": 0, "created_relations": 0, "skipped_records": 0}
        try:
            data = store.get_dataset(dataset_id)
            for record in request.records:
                evidence_id = f"{dataset_id}:{record.record_id}"
                if evidence_id in data.evidence:
                    created["skipped_records"] += 1
                    continue
                relations = [RelationInput(id=f"{dataset_id}:{record.record_id}:{index}", relation_type=item.relation_type, source_id=item.source_ref, target_id=item.target_ref, weight=item.weight, attributes=item.attributes, evidence_ids=[evidence_id]) for index, item in enumerate(record.relations)]
                _validate_relation_endpoints(data.schema, record.entities, relations, data.entities)
                result = store.ingest(dataset_id, record.entities, [EvidenceInput(id=evidence_id, source_record_id=record.record_id, **record.evidence)], relations)
                created["created_entities"] += result["entities"]
                created["created_evidence"] += result["evidence"]
                created["created_relations"] += result["relations"]
            return created
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset not found") from error
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/query")
    def query_graph(intent: QueryIntent, store: MemoryGraphStore = Depends(get_graph_service)) -> dict[str, Any]:
        try:
            data = store.get_dataset(intent.dataset_id)
            _validate_intent(data.schema, intent)
            if intent.intent == "find_entity":
                results: Any = store.search(intent.dataset_id, intent.entity_type, intent.filters, intent.limit)
            elif intent.intent == "get_evidence":
                if not intent.entity_id:
                    raise ValueError("entity_id is required for get_evidence")
                results = store.evidence_for(intent.dataset_id, intent.entity_id)
            else:
                results = []
            return {"intent": intent.intent, "dataset_id": intent.dataset_id, "results": results}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset or entity not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return application


def get_graph_service() -> Generator[MemoryGraphStore, None, None]:
    yield app.state.graph_service


def _public_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in schema.items() if key not in {"dataset_id", "graph_version"}}


def _validate_relation_endpoints(schema: DatasetSchemaInput, incoming: list[Any], relations: list[RelationInput], existing: dict[str, dict[str, Any]]) -> None:
    entity_types = {item.id: item.entity_type for item in incoming} | {key: value["entity_type"] for key, value in existing.items()}
    relation_types = {item.name: item for item in schema.relation_types}
    for relation in relations:
        config = relation_types.get(relation.relation_type)
        if config is None:
            continue
        if config.source_types and entity_types.get(relation.source_id) not in config.source_types:
            raise ValueError("relation source type is not allowed by the dataset schema")
        if config.target_types and entity_types.get(relation.target_id) not in config.target_types:
            raise ValueError("relation target type is not allowed by the dataset schema")


def _validate_intent(schema: DatasetSchemaInput, intent: QueryIntent) -> None:
    types = {item.name: item for item in schema.entity_types}
    if intent.entity_type and intent.entity_type not in types:
        raise ValueError("unknown entity type")
    if intent.relation_type and intent.relation_type not in {item.name for item in schema.relation_types}:
        raise ValueError("unknown relation type")
    allowed = {"id", "display_name"}
    if intent.entity_type:
        config = types[intent.entity_type]
        allowed.update(config.identifier_fields)
        allowed.update(config.queryable_fields)
    if any(item.field not in allowed for item in intent.filters):
        raise ValueError("filter field is not queryable for this entity type")


app = create_app()
