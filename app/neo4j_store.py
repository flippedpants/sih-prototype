"""Neo4j persistence adapter for the generic graph model.

Dataset-specific fields are JSON properties, so dataset evolution does not need
database migrations. Only stable generic IDs are constrained at bootstrap.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import networkx as nx
from neo4j import GraphDatabase

from .models import DatasetSchemaInput, EntityInput, EvidenceInput, RelationInput
from .store import DatasetData


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.bootstrap()

    def close(self) -> None:
        self.driver.close()

    def bootstrap(self) -> None:
        queries = (
            "CREATE CONSTRAINT dataset_id IF NOT EXISTS FOR (n:Dataset) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT evidence_key IF NOT EXISTS FOR (n:Evidence) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT relation_key IF NOT EXISTS FOR (n:Relation) REQUIRE n.key IS UNIQUE",
        )
        with self.driver.session() as session:
            for query in queries:
                session.run(query).consume()

    def register_dataset(self, schema: DatasetSchemaInput) -> dict[str, Any]:
        payload = schema.model_dump(mode="json")
        with self.driver.session() as session:
            record = session.run("MATCH (d:Dataset {id: $id}) RETURN d.schema_json AS schema", id=schema.dataset_id).single()
            if record:
                if json.loads(record["schema"]) != payload:
                    raise ValueError("dataset_id already exists with a different schema")
                return self.schema_dict(self.get_dataset(schema.dataset_id))
            session.run("CREATE (:Dataset {id: $id, schema_json: $schema, version: 0})", id=schema.dataset_id, schema=json.dumps(payload, sort_keys=True)).consume()
        return self.schema_dict(self.get_dataset(schema.dataset_id))

    def get_dataset(self, dataset_id: str) -> DatasetData:
        with self.driver.session() as session:
            record = session.run("MATCH (d:Dataset {id: $id}) RETURN d.schema_json AS schema, d.version AS version", id=dataset_id).single()
        if not record:
            raise KeyError("dataset not found")
        return DatasetData(schema=DatasetSchemaInput(**json.loads(record["schema"])), version=record["version"])

    def schema_dict(self, data: DatasetData) -> dict[str, Any]:
        result = data.schema.model_dump(mode="json")
        result["graph_version"] = data.version
        return result

    def ingest(self, dataset_id: str, entities: list[EntityInput], evidence: list[EvidenceInput], relations: list[RelationInput]) -> dict[str, int]:
        # Validation is performed by the API before this persistence adapter runs.
        with self.driver.session() as session:
            def write(tx: Any) -> None:
                for entity in entities:
                    tx.run("MERGE (e:Entity {key: $key}) SET e += $props", key=_key(dataset_id, entity.id), props={"id": entity.id, "dataset_id": dataset_id, "entity_type": entity.entity_type, "display_name": entity.display_name, "identifiers_json": json.dumps(entity.identifiers, sort_keys=True), "attributes_json": json.dumps(entity.attributes, sort_keys=True)})
                for item in evidence:
                    tx.run("MERGE (e:Evidence {key: $key}) SET e += $props", key=_key(dataset_id, item.id), props={"id": item.id, "dataset_id": dataset_id, "source_record_id": item.source_record_id, "source_kind": item.source_kind, "confidence": item.confidence, "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None, "attributes_json": json.dumps(item.attributes, sort_keys=True), "raw_payload_ref": item.raw_payload_ref})
                for relation in relations:
                    tx.run("MATCH (source:Entity {key: $source}), (target:Entity {key: $target}) MERGE (r:Relation {key: $key}) SET r += $props MERGE (source)-[:SOURCE]->(r) MERGE (r)-[:TARGET]->(target)", source=_key(dataset_id, relation.source_id), target=_key(dataset_id, relation.target_id), key=_key(dataset_id, relation.id), props={"id": relation.id, "dataset_id": dataset_id, "relation_type": relation.relation_type, "weight": relation.weight, "derived": relation.derived, "attributes_json": json.dumps(relation.attributes, sort_keys=True)})
                    for evidence_id in relation.evidence_ids:
                        tx.run("MATCH (e:Evidence {key: $evidence}), (r:Relation {key: $relation}) MERGE (e)-[:SUPPORTS]->(r)", evidence=_key(dataset_id, evidence_id), relation=_key(dataset_id, relation.id))
                tx.run("MATCH (d:Dataset {id: $id}) SET d.version = d.version + 1", id=dataset_id)
            session.execute_write(write)
        return {"entities": len(entities), "evidence": len(evidence), "relations": len(relations), "graph_version": self.get_dataset(dataset_id).version}

    def search(self, dataset_id: str, entity_type: str | None = None, filters: list[Any] | None = None, limit: int = 25) -> list[dict[str, Any]]:
        # Fields are registry-validated by the API; filtering JSON is deliberately
        # done here after a bounded fetch so arbitrary dataset fields stay migration-free.
        with self.driver.session() as session:
            rows = session.run("MATCH (e:Entity {dataset_id: $id}) WHERE $type IS NULL OR e.entity_type = $type RETURN e LIMIT $limit", id=dataset_id, type=entity_type, limit=limit * 4)
            items = [_entity_from_node(row["e"]) for row in rows]
        return [item for item in items if _matches(item, filters or [])][:limit]

    def entity(self, dataset_id: str, entity_id: str) -> dict[str, Any]:
        with self.driver.session() as session:
            row = session.run("MATCH (e:Entity {key: $key}) RETURN e", key=_key(dataset_id, entity_id)).single()
        if not row:
            raise KeyError("entity not found")
        return _entity_from_node(row["e"])

    def evidence_for(self, dataset_id: str, entity_id: str) -> list[dict[str, Any]]:
        query = "MATCH (entity:Entity {key: $entity})-[:SOURCE]->(r:Relation)<-[:SUPPORTS]-(e:Evidence) RETURN DISTINCT e"
        with self.driver.session() as session:
            return [_evidence_from_node(row["e"]) for row in session.run(query, entity=_key(dataset_id, entity_id))]

    def graph(self, dataset_id: str) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        with self.driver.session() as session:
            for row in session.run("MATCH (e:Entity {dataset_id: $id}) RETURN e", id=dataset_id):
                entity = _entity_from_node(row["e"])
                graph.add_node(entity["id"], **entity)
            query = "MATCH (source:Entity {dataset_id: $id})-[:SOURCE]->(r:Relation)-[:TARGET]->(target:Entity {dataset_id: $id}) RETURN source.id AS source, target.id AS target, r"
            for row in session.run(query, id=dataset_id):
                relation = dict(row["r"])
                graph.add_edge(row["source"], row["target"], key=relation["id"], **relation)
        return graph


def _key(dataset_id: str, identifier: str) -> str:
    return f"{dataset_id}:{identifier}"


def _entity_from_node(node: Any) -> dict[str, Any]:
    value = dict(node)
    value["identifiers"] = json.loads(value.pop("identifiers_json"))
    value["attributes"] = json.loads(value.pop("attributes_json"))
    value.pop("key", None)
    return deepcopy(value)


def _evidence_from_node(node: Any) -> dict[str, Any]:
    value = dict(node)
    value["attributes"] = json.loads(value.pop("attributes_json"))
    value.pop("key", None)
    return deepcopy(value)


def _matches(entity: dict[str, Any], filters: list[Any]) -> bool:
    values = entity.get("attributes", {}) | entity.get("identifiers", {}) | {"id": entity["id"], "display_name": entity.get("display_name")}
    for item in filters:
        actual = values.get(item.field)
        if item.operator == "eq" and actual != item.value:
            return False
        if item.operator == "contains" and str(item.value).lower() not in str(actual).lower():
            return False
        if item.operator == "in" and actual not in item.value:
            return False
    return True
