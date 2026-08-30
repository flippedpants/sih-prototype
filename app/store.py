"""Storage adapter. The in-memory implementation makes the API usable without Neo4j."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
import networkx as nx

from .models import DatasetSchemaInput, EntityInput, EvidenceInput, RelationInput


@dataclass
class DatasetData:
    schema: DatasetSchemaInput
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    relations: dict[str, dict[str, Any]] = field(default_factory=dict)
    version: int = 0


class MemoryGraphStore:
    """Idempotent generic graph store; a Neo4j adapter can implement this interface later."""

    def __init__(self) -> None:
        self.datasets: dict[str, DatasetData] = {}

    def register_dataset(self, schema: DatasetSchemaInput) -> dict[str, Any]:
        existing = self.datasets.get(schema.dataset_id)
        if existing:
            if existing.schema.model_dump() != schema.model_dump():
                raise ValueError("dataset_id already exists with a different schema")
            return self.schema_dict(existing)
        data = DatasetData(schema=schema)
        self.datasets[schema.dataset_id] = data
        return self.schema_dict(data)

    def get_dataset(self, dataset_id: str) -> DatasetData:
        if dataset_id not in self.datasets:
            raise KeyError("dataset not found")
        return self.datasets[dataset_id]

    def schema_dict(self, data: DatasetData) -> dict[str, Any]:
        result = data.schema.model_dump()
        result["graph_version"] = data.version
        return result

    def ingest(self, dataset_id: str, entities: list[EntityInput], evidence: list[EvidenceInput], relations: list[RelationInput]) -> dict[str, int]:
        data = self.get_dataset(dataset_id)
        entity_types = {x.name for x in data.schema.entity_types}
        relation_types = {x.name for x in data.schema.relation_types}
        for entity in entities:
            if entity.entity_type not in entity_types:
                raise ValueError(f"unknown entity type: {entity.entity_type}")
        for relation in relations:
            if relation.relation_type not in relation_types:
                raise ValueError(f"unknown relation type: {relation.relation_type}")
        incoming_entity_ids = {e.id for e in entities}
        for relation in relations:
            if relation.source_id not in data.entities and relation.source_id not in incoming_entity_ids:
                raise ValueError(f"unknown source entity: {relation.source_id}")
            if relation.target_id not in data.entities and relation.target_id not in incoming_entity_ids:
                raise ValueError(f"unknown target entity: {relation.target_id}")
        incoming_evidence_ids = {e.id for e in evidence}
        for relation in relations:
            unknown = [x for x in relation.evidence_ids if x not in data.evidence and x not in incoming_evidence_ids]
            if unknown:
                raise ValueError(f"unknown evidence IDs: {', '.join(unknown)}")

        before = (len(data.entities), len(data.evidence), len(data.relations))
        for item in entities:
            record = item.model_dump(mode="json") | {"dataset_id": dataset_id}
            data.entities[item.id] = record
        for item in evidence:
            record = item.model_dump(mode="json") | {"dataset_id": dataset_id}
            data.evidence[item.id] = record
        for item in relations:
            record = item.model_dump(mode="json") | {"dataset_id": dataset_id}
            data.relations[item.id] = record
        after = (len(data.entities), len(data.evidence), len(data.relations))
        if after != before:
            data.version += 1
        return {"entities": len(entities), "evidence": len(evidence), "relations": len(relations), "graph_version": data.version}

    def graph(self, dataset_id: str) -> nx.MultiDiGraph:
        data = self.get_dataset(dataset_id)
        graph = nx.MultiDiGraph()
        for key, entity in data.entities.items():
            graph.add_node(key, **entity)
        relation_type_cfg = {item.name: item for item in data.schema.relation_types}
        for key, relation in data.relations.items():
            graph.add_edge(relation["source_id"], relation["target_id"], key=key, **relation)
            if not relation_type_cfg[relation["relation_type"]].directed:
                reverse = deepcopy(relation)
                reverse["source_id"], reverse["target_id"] = reverse["target_id"], reverse["source_id"]
                graph.add_edge(reverse["source_id"], reverse["target_id"], key=f"{key}:reverse", **reverse)
        return graph

    def entity(self, dataset_id: str, entity_id: str) -> dict[str, Any]:
        data = self.get_dataset(dataset_id)
        if entity_id not in data.entities:
            raise KeyError("entity not found")
        return deepcopy(data.entities[entity_id])

    def search(self, dataset_id: str, entity_type: str | None = None, filters: list[Any] | None = None, limit: int = 25) -> list[dict[str, Any]]:
        data = self.get_dataset(dataset_id)
        results = []
        for entity in data.entities.values():
            if entity_type and entity["entity_type"] != entity_type:
                continue
            if filters and not self._matches(entity, filters):
                continue
            results.append(deepcopy(entity))
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _matches(entity: dict[str, Any], filters: list[Any]) -> bool:
        values = entity.get("attributes", {}) | entity.get("identifiers", {}) | {"id": entity["id"], "display_name": entity.get("display_name")}
        for filt in filters:
            actual = values.get(filt.field)
            if filt.operator == "eq" and actual != filt.value:
                return False
            if filt.operator == "contains" and str(filt.value).lower() not in str(actual).lower():
                return False
            if filt.operator == "in" and actual not in filt.value:
                return False
        return True

    def evidence_for(self, dataset_id: str, entity_id: str) -> list[dict[str, Any]]:
        data = self.get_dataset(dataset_id)
        evidence_ids = set()
        for relation in data.relations.values():
            if entity_id in (relation["source_id"], relation["target_id"]):
                evidence_ids.update(relation["evidence_ids"])
        return [deepcopy(data.evidence[x]) for x in evidence_ids if x in data.evidence]
