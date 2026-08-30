"""Schema and normalized objects for declarative structured-source ingestion."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ENTITY_TYPES = frozenset({"PERSON", "PHONE", "ACCOUNT", "VEHICLE", "ORG", "LOCATION"})
RELATIONSHIP_TYPES = frozenset({"CALLED", "TRANSFERRED_TO", "OWNS", "ASSOCIATED_WITH", "NAMED_IN_FIR"})


class EdgeEntityReference(BaseModel):
    column: str = Field(min_length=1)
    entity_type: str

    @model_validator(mode="after")
    def controlled_type(self) -> "EdgeEntityReference":
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity_type: {self.entity_type}")
        return self


class EntityBlock(BaseModel):
    entity_type: str
    id_column: str = Field(min_length=1)
    canonical_name_column: str | None = None
    attribute_columns: list[str] = Field(default_factory=list)
    aliases_column: str | None = None

    @model_validator(mode="after")
    def controlled_type(self) -> "EntityBlock":
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity_type: {self.entity_type}")
        return self


class RelationshipBlock(BaseModel):
    type: str
    source_column: str = Field(min_length=1)
    target_column: str = Field(min_length=1)
    weight_columns: list[str] = Field(default_factory=list)
    timestamp_column: str | None = None

    @model_validator(mode="after")
    def controlled_type(self) -> "RelationshipBlock":
        if self.type not in RELATIONSHIP_TYPES:
            raise ValueError(f"unsupported relationship type: {self.type}")
        return self


class SourceMapping(BaseModel):
    source_type: str = Field(min_length=1)
    row_maps_to: Literal["entity", "edge", "mixed"]
    entity_type: str | None = None
    id_column: str | None = None
    attribute_columns: list[str] = Field(default_factory=list)
    aliases_column: str | None = None
    canonical_name_column: str | None = None
    entities: list[EdgeEntityReference | EntityBlock] = Field(default_factory=list)
    relationship: RelationshipBlock | None = None
    relationships: list[RelationshipBlock] = Field(default_factory=list)
    allow_extra_columns: bool = True

    @model_validator(mode="after")
    def shape_is_valid(self) -> "SourceMapping":
        if self.row_maps_to == "entity":
            if not self.entity_type or not self.id_column:
                raise ValueError("entity mappings require entity_type and id_column")
            if self.entity_type not in ENTITY_TYPES:
                raise ValueError(f"unsupported entity_type: {self.entity_type}")
        elif self.row_maps_to == "edge":
            if not self.entities or not self.relationship:
                raise ValueError("edge mappings require entities and relationship")
            if any(not isinstance(item, EdgeEntityReference) for item in self.entities):
                raise ValueError("edge mapping entities require column and entity_type")
        else:
            if not self.entities:
                raise ValueError("mixed mappings require entities")
            if any(not isinstance(item, EntityBlock) for item in self.entities):
                raise ValueError("mixed mapping entities require entity_type and id_column")
        return self

    def entity_blocks(self) -> list[EntityBlock]:
        if self.row_maps_to == "entity":
            return [EntityBlock(entity_type=self.entity_type or "", id_column=self.id_column or "", canonical_name_column=self.canonical_name_column, attribute_columns=self.attribute_columns, aliases_column=self.aliases_column)]
        if self.row_maps_to == "mixed":
            return [item for item in self.entities if isinstance(item, EntityBlock)]
        return [EntityBlock(entity_type=item.entity_type, id_column=item.column) for item in self.entities if isinstance(item, EdgeEntityReference)]

    def relationship_blocks(self) -> list[RelationshipBlock]:
        if self.row_maps_to == "edge":
            return [self.relationship] if self.relationship else []
        return self.relationships


class Entity(BaseModel):
    id: str
    type: str
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    source_docs: list[str] = Field(default_factory=list)


class Relationship(BaseModel):
    source_id: str
    target_id: str
    type: str
    weight: float = 1.0
    source_doc: str
    timestamp: datetime | None = None


class RowValidationError(BaseModel):
    row_number: int
    reason: str


class IngestionResult(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    validation_errors: list[RowValidationError] = Field(default_factory=list)
