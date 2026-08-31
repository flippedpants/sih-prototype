"""Public request and response contracts. Domain fields live in attributes."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EntityType(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_ -]*$")
    identifier_fields: list[str] = Field(default_factory=list)
    display_field: str | None = None
    queryable_fields: list[str] = Field(default_factory=list)


class RelationType(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_ -]*$")
    directed: bool = True
    weight_field: str | None = None
    source_types: list[str] = Field(default_factory=list)
    target_types: list[str] = Field(default_factory=list)


class DatasetSchemaInput(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    name: str | None = None
    entity_types: list[EntityType] = Field(min_length=1)
    relation_types: list[RelationType] = Field(default_factory=list)
    description: str | None = None

    @field_validator("entity_types")
    @classmethod
    def unique_entity_types(cls, values: list[EntityType]) -> list[EntityType]:
        if len({item.name.lower() for item in values}) != len(values):
            raise ValueError("entity type names must be unique")
        return values

    @model_validator(mode="after")
    def relation_endpoints_must_be_declared(self) -> "DatasetSchemaInput":
        declared = {item.name for item in self.entity_types}
        for relation in self.relation_types:
            unknown = set(relation.source_types + relation.target_types) - declared
            if unknown:
                raise ValueError(
                    f"relation type {relation.name} references undeclared entity types: {', '.join(sorted(unknown))}"
                )
        return self


class EntityInput(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1)
    display_name: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)


class EvidenceInput(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    source_record_id: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(min_length=1, max_length=100)
    confidence: float = Field(default=1.0, ge=0, le=1)
    occurred_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_payload_ref: str | None = None


class RelationInput(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    relation_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0)
    evidence_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    derived: bool = False


class IngestRequest(BaseModel):
    version: str = Field(default="1")
    entities: list[EntityInput] = Field(default_factory=list)
    evidence: list[EvidenceInput] = Field(default_factory=list)
    relations: list[RelationInput] = Field(default_factory=list)


class DatasetRegistration(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    dataset_schema: dict[str, Any] = Field(alias="schema")


class SourceRelationInput(BaseModel):
    relation_type: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    target_ref: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SourceRecordInput(BaseModel):
    record_id: str = Field(min_length=1, max_length=200)
    entities: list[EntityInput] = Field(default_factory=list)
    relations: list[SourceRelationInput] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecordsIngestionRequest(BaseModel):
    records: list[SourceRecordInput] = Field(min_length=1)


class CsvEntityMapping(BaseModel):
    id_column: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    display_name_column: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    attributes: dict[str, str] = Field(default_factory=dict)


class CsvRelationMapping(BaseModel):
    relation_type: str = Field(min_length=1)
    source_id_column: str = Field(min_length=1)
    target_id_column: str = Field(min_length=1)
    weight_column: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class CsvEvidenceMapping(BaseModel):
    source_kind: str = Field(default="csv", min_length=1)
    confidence_column: str | None = None
    occurred_at_column: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class CsvFileMapping(BaseModel):
    file_name: str = Field(min_length=1)
    record_id_column: str = Field(min_length=1)
    entities: list[CsvEntityMapping] = Field(min_length=1)
    relations: list[CsvRelationMapping] = Field(default_factory=list)
    evidence: CsvEvidenceMapping = Field(default_factory=CsvEvidenceMapping)


class CsvIngestionMapping(BaseModel):
    files: list[CsvFileMapping] = Field(min_length=1)

    @field_validator("files")
    @classmethod
    def unique_file_names(cls, values: list[CsvFileMapping]) -> list[CsvFileMapping]:
        if len({item.file_name for item in values}) != len(values):
            raise ValueError("each CSV file must have exactly one mapping")
        return values


class IntentFilter(BaseModel):
    field: str = Field(min_length=1)
    operator: Literal["eq", "contains", "in"] = "eq"
    value: str | int | float | bool | list[str | int | float | bool]


class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal[
        "find_entity", "neighbors", "connection_path", "rank_influencers", "list_communities", "get_evidence",
        "full_graph", "cluster_graph", "list_clusters", "entity_details", "search_entities", "statistics",
    ]
    dataset_id: str = Field(min_length=1)
    entity_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    entity_type: str | None = None
    relation_type: str | None = None
    cluster_id: str | None = None
    query: str | None = None
    filters: list[IntentFilter] = Field(default_factory=list)
    limit: int = Field(default=25, ge=1, le=100)

    @field_validator("filters")
    @classmethod
    def disallow_query_syntax_in_filter_values(cls, filters: list[IntentFilter]) -> list[IntentFilter]:
        forbidden = ("match ", "detach ", "delete ", "create ", "merge ", "call ", ";", "//")
        for item in filters:
            values = item.value if isinstance(item.value, list) else [item.value]
            for value in values:
                if isinstance(value, str) and any(token in value.lower() for token in forbidden):
                    raise ValueError("query syntax is not allowed in filter values")
        return filters
