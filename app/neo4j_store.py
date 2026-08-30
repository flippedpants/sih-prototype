"""Neo4j persistence adapter for the generic graph model.

Dataset-specific fields are JSON properties, so dataset evolution does not need
database migrations. Only stable generic IDs are constrained at bootstrap.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from neo4j import GraphDatabase

from .models import DatasetSchemaInput, EntityInput, EvidenceInput, RelationInput
from dataclasses import dataclass

@dataclass
class DatasetData:
    schema: DatasetSchemaInput
    version: int = 0


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
                    tx.run("MERGE (e:Entity {key: $key}) SET e += $props", key=_key(dataset_id, entity.id), props={"id": entity.id, "dataset_id": dataset_id, "entity_type": entity.entity_type, "display_name": entity.display_name, "identifiers_json": json.dumps(entity.identifiers, sort_keys=True), "attributes_json": json.dumps(entity.attributes, sort_keys=True), "filter_values": _filter_values(entity)})
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

    def evidence_exists(self, dataset_id: str, evidence_id: str) -> bool:
        with self.driver.session() as session:
            return session.run("MATCH (:Evidence {key: $key}) RETURN count(*) AS count", key=_key(dataset_id, evidence_id)).single()["count"] > 0

    def entity_types(self, dataset_id: str, entity_ids: list[str]) -> dict[str, str]:
        if not entity_ids:
            return {}
        with self.driver.session() as session:
            rows = session.run("MATCH (e:Entity {dataset_id: $dataset_id}) WHERE e.id IN $ids RETURN e.id AS id, e.entity_type AS type", dataset_id=dataset_id, ids=entity_ids)
            return {row["id"]: row["type"] for row in rows}

    def query(self, intent: Any) -> list[Any]:
        if intent.intent == "find_entity":
            return self._find_entities(intent)
        if intent.intent == "get_evidence":
            if not intent.entity_id:
                raise ValueError("entity_id is required for get_evidence")
            return self.evidence_for(intent.dataset_id, intent.entity_id)
        if intent.intent == "neighbors":
            if not intent.entity_id:
                raise ValueError("entity_id is required for neighbors")
            query = "MATCH (entity:Entity {key: $key})-[:SOURCE|TARGET]-(r:Relation)-[:SOURCE|TARGET]-(neighbor:Entity {dataset_id: $dataset_id}) WHERE neighbor <> entity RETURN DISTINCT neighbor ORDER BY neighbor.id LIMIT $limit"
            with self.driver.session() as session:
                return [_entity_from_node(row["neighbor"]) for row in session.run(query, key=_key(intent.dataset_id, intent.entity_id), dataset_id=intent.dataset_id, limit=intent.limit)]
        if intent.intent == "connection_path":
            if not intent.source_id or not intent.target_id:
                raise ValueError("source_id and target_id are required for connection_path")
            query = "MATCH (source:Entity {key: $source}), (target:Entity {key: $target}) MATCH path = shortestPath((source)-[:SOURCE|TARGET*..20]-(target)) RETURN [node IN nodes(path) WHERE node:Entity | node.id] AS ids"
            with self.driver.session() as session:
                row = session.run(query, source=_key(intent.dataset_id, intent.source_id), target=_key(intent.dataset_id, intent.target_id)).single()
            if not row:
                raise KeyError("connection path not found")
            return row["ids"]
        if intent.intent == "rank_influencers":
            query = "MATCH (entity:Entity {dataset_id: $dataset_id}) OPTIONAL MATCH (entity)-[:SOURCE|TARGET]-(:Relation) WITH entity, count(*) AS score RETURN entity.id AS id, toFloat(score) AS score ORDER BY score DESC, id ASC LIMIT $limit"
            with self.driver.session() as session:
                return [dict(row) for row in session.run(query, dataset_id=intent.dataset_id, limit=intent.limit)]
        if intent.intent == "list_communities":
            return self._communities(intent.dataset_id, intent.limit)
        raise ValueError("unsupported query intent")

    def _find_entities(self, intent: Any) -> list[dict[str, Any]]:
        clauses, parameters = [], {"dataset_id": intent.dataset_id, "entity_type": intent.entity_type, "limit": intent.limit}
        for index, filter_item in enumerate(intent.filters):
            key = f"filter_{index}"
            prefix = f"{filter_item.field}\u001f"
            if filter_item.operator == "eq":
                clauses.append(f"${key} IN entity.filter_values")
                parameters[key] = prefix + json.dumps(filter_item.value, sort_keys=True)
            elif filter_item.operator == "contains":
                clauses.append(f"any(value IN entity.filter_values WHERE value STARTS WITH ${key} AND toLower(value) CONTAINS toLower(${key}_value))")
                parameters[key], parameters[f"{key}_value"] = prefix, str(filter_item.value)
            else:
                clauses.append(f"any(value IN ${key} WHERE value IN entity.filter_values)")
                parameters[key] = [prefix + json.dumps(value, sort_keys=True) for value in filter_item.value]
        where = " AND ".join(clauses) if clauses else "true"
        query = f"MATCH (entity:Entity {{dataset_id: $dataset_id}}) WHERE ($entity_type IS NULL OR entity.entity_type = $entity_type) AND {where} RETURN entity ORDER BY entity.id LIMIT $limit"
        with self.driver.session() as session:
            return [_entity_from_node(row["entity"]) for row in session.run(query, **parameters)]

    def _communities(self, dataset_id: str, limit: int) -> list[list[str]]:
        name = f"community_{dataset_id.replace('-', '_')}"
        node_query = "MATCH (entity:Entity {dataset_id: $dataset_id}) RETURN id(entity) AS id"
        relation_query = "MATCH (source:Entity {dataset_id: $dataset_id})-[:SOURCE]->(:Relation)-[:TARGET]->(target:Entity {dataset_id: $dataset_id}) RETURN id(source) AS source, id(target) AS target"
        with self.driver.session() as session:
            session.run("CALL gds.graph.project.cypher($name, $nodes, $relations, {parameters: {dataset_id: $dataset_id}})", name=name, nodes=node_query, relations=relation_query, dataset_id=dataset_id).consume()
            try:
                rows = session.run("CALL gds.louvain.stream($name) YIELD nodeId, communityId MATCH (entity:Entity) WHERE id(entity) = nodeId RETURN communityId, entity.id AS id ORDER BY communityId, id", name=name)
                groups: dict[int, list[str]] = {}
                for row in rows:
                    groups.setdefault(row["communityId"], []).append(row["id"])
                return list(groups.values())[:limit]
            finally:
                session.run("CALL gds.graph.drop($name, false)", name=name).consume()


def _filter_values(entity: EntityInput) -> list[str]:
    values = entity.attributes | entity.identifiers | ({"display_name": entity.display_name} if entity.display_name is not None else {})
    return [f"{field}\u001f{json.dumps(value, sort_keys=True)}" for field, value in values.items()]


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
