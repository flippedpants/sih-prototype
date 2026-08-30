"""FastAPI entry point for the metadata-driven graph backend."""
from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status

from .models import (
    DatasetRegistration,
    DatasetSchemaInput,
    EvidenceInput,
    QueryIntent,
    RecordsIngestionRequest,
    RelationInput,
)
from .csv_ingestion import parse_csv_uploads
from .source_ingestion.engine import SourceIngestionEngine
from .source_ingestion.loader import load_mapping
from .source_ingestion.validation import StructuralValidationError
from .neo4j_store import Neo4jGraphStore


def create_app(graph_store: Any | None = None) -> FastAPI:
    application = FastAPI(title="Graph Intelligence API", version="0.1.0")
    application.state.graph_service = graph_store or Neo4jGraphStore(os.getenv("NEO4J_URI", "bolt://localhost:7687"), os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "change-me-now"))

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "store": "neo4j"}

    @application.post("/api/datasets", status_code=status.HTTP_201_CREATED)
    def register_dataset(request: DatasetRegistration, store: Any = Depends(get_graph_service)) -> dict[str, Any]:
        try:
            schema = DatasetSchemaInput(dataset_id=request.dataset_id, **request.dataset_schema)
            registered = store.register_dataset(schema)
            return {"dataset_id": request.dataset_id, "schema": _public_schema(registered)}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/datasets/{dataset_id}")
    def get_dataset(dataset_id: str, store: Any = Depends(get_graph_service)) -> dict[str, Any]:
        try:
            return {"dataset_id": dataset_id, "schema": _public_schema(store.schema_dict(store.get_dataset(dataset_id)))}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset not found") from error

    @application.post("/api/datasets/{dataset_id}/ingestions")
    def ingest_records(dataset_id: str, request: RecordsIngestionRequest, store: Any = Depends(get_graph_service)) -> dict[str, int]:
        try:
            return _ingest_source_records(dataset_id, request.records, store)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset not found") from error
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/datasets/{dataset_id}/ingestions/csv")
    async def ingest_csv_files(
        dataset_id: str,
        files: list[UploadFile] = File(...),
        mapping: str = Form(...),
        store: Any = Depends(get_graph_service),
    ) -> dict[str, int]:
        try:
            import json

            records = parse_csv_uploads(
                [(file.filename or "upload.csv", await file.read()) for file in files],
                json.loads(mapping),
            )
            return _ingest_source_records(dataset_id, records, store) | {"processed_files": len(files)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset not found") from error
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/datasets/{dataset_id}/ingestions/sources/{source_type}")
    async def ingest_structured_source(
        dataset_id: str,
        source_type: str,
        file: UploadFile = File(...),
        store: Any = Depends(get_graph_service),
    ) -> dict[str, Any]:
        try:
            mapping = load_mapping(source_type)
            result = SourceIngestionEngine().ingest_bytes(file.filename or "upload.csv", await file.read(), mapping)
            data = store.get_dataset(dataset_id)
            _validate_source_batch(data.schema, result.entities, result.relationships)
            written = {"entities": 0, "relationships": 0}
            if result.entities or result.relationships:
                written = store.ingest_source_batch(dataset_id, result.entities, result.relationships)
            return {
                "source_type": source_type,
                "processed_file": file.filename or "upload.csv",
                "created_entities": written["entities"],
                "created_relationships": written["relationships"],
                "validation_errors": [item.model_dump() for item in result.validation_errors],
            }
        except KeyError as error:
            detail = "dataset not found" if str(error).strip("'\"") == dataset_id else str(error).strip("'\"")
            raise HTTPException(status_code=404, detail=detail) from error
        except StructuralValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/query")
    def query_graph(intent: QueryIntent, store: Any = Depends(get_graph_service)) -> dict[str, Any]:
        try:
            data = store.get_dataset(intent.dataset_id)
            _validate_intent(data.schema, intent)
            results = store.query(intent)
            return {"intent": intent.intent, "dataset_id": intent.dataset_id, "results": results}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="dataset or entity not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return application


def get_graph_service(request: Request) -> Generator[Any, None, None]:
    yield request.app.state.graph_service



def _ingest_source_records(dataset_id: str, records: list[Any], store: Any) -> dict[str, int]:
    created = {"created_entities": 0, "created_evidence": 0, "created_relations": 0, "skipped_records": 0}
    data = store.get_dataset(dataset_id)
    for record in records:
        evidence_id = f"{dataset_id}:{record.record_id}"
        if store.evidence_exists(dataset_id, evidence_id):
            created["skipped_records"] += 1
            continue
        _validate_entity_types(data.schema, record.entities)
        relations = [
            RelationInput(
                id=f"{dataset_id}:{record.record_id}:{index}",
                relation_type=item.relation_type,
                source_id=item.source_ref,
                target_id=item.target_ref,
                weight=item.weight,
                attributes=item.attributes,
                evidence_ids=[evidence_id],
            )
            for index, item in enumerate(record.relations)
        ]
        _validate_relation_endpoints(
            data.schema,
            record.entities,
            relations,
            store.entity_types(dataset_id, [item.source_id for item in relations] + [item.target_id for item in relations]),
        )
        result = store.ingest(
            dataset_id,
            record.entities,
            [EvidenceInput(id=evidence_id, source_record_id=record.record_id, **record.evidence)],
            relations,
        )
        created["created_entities"] += result["entities"]
        created["created_evidence"] += result["evidence"]
        created["created_relations"] += result["relations"]
    return created

def _public_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in schema.items() if key not in {"dataset_id", "graph_version"}}


def _validate_relation_endpoints(schema: DatasetSchemaInput, incoming: list[Any], relations: list[RelationInput], existing: dict[str, str]) -> None:
    entity_types = {item.id: item.entity_type for item in incoming} | existing
    relation_types = {item.name: item for item in schema.relation_types}
    for relation in relations:
        config = relation_types.get(relation.relation_type)
        if config is None:
            continue
        if config.source_types and entity_types.get(relation.source_id) not in config.source_types:
            raise ValueError("relation source type is not allowed by the dataset schema")
        if config.target_types and entity_types.get(relation.target_id) not in config.target_types:
            raise ValueError("relation target type is not allowed by the dataset schema")



def _validate_entity_types(schema: DatasetSchemaInput, entities: list[Any]) -> None:
    allowed = {item.name for item in schema.entity_types}
    unknown = sorted({item.entity_type for item in entities} - allowed)
    if unknown:
        raise ValueError(f"unknown entity types: {', '.join(unknown)}")

def _validate_source_batch(schema: DatasetSchemaInput, entities: list[Any], relationships: list[Any]) -> None:
    allowed_entities = {item.name for item in schema.entity_types}
    unknown_entities = sorted({item.type for item in entities} - allowed_entities)
    if unknown_entities:
        raise ValueError(f"source mapping entity types are absent from the dataset schema: {', '.join(unknown_entities)}")
    allowed_relationships = {item.name for item in schema.relation_types}
    unknown_relationships = sorted({item.type for item in relationships} - allowed_relationships)
    if unknown_relationships:
        raise ValueError(f"source mapping relationship types are absent from the dataset schema: {', '.join(unknown_relationships)}")


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


