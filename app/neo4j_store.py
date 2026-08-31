"""Neo4j persistence adapter for the generic graph model.

Dataset-specific fields are JSON properties, so dataset evolution does not need
database migrations. Only stable generic IDs are constrained at bootstrap.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import deque
from copy import deepcopy
from typing import Any

from neo4j import GraphDatabase

from .models import DatasetSchemaInput, EntityInput, EvidenceInput, RelationInput
from .source_ingestion.models import Entity as SourceEntity, Relationship as SourceRelationship
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

    def ingest_source_batch(
        self,
        dataset_id: str,
        entities: list[SourceEntity],
        relationships: list[SourceRelationship],
        batch_size: int = 1_000,
    ) -> dict[str, int]:
        """Persist normalized source objects using bounded UNWIND batches."""
        entity_rows = [
            {
                "key": _key(dataset_id, entity.id),
                "id": entity.id,
                "dataset_id": dataset_id,
                "entity_type": entity.type,
                "display_name": entity.canonical_name,
                "identifiers_json": json.dumps({"natural_key": entity.id.split(":", 1)[1]}, sort_keys=True),
                "attributes_json": json.dumps(entity.attributes, sort_keys=True),
                "filter_values": _batch_filter_values(entity),
                "aliases": entity.aliases,
                "source_docs": entity.source_docs,
            }
            for entity in entities
        ]
        relation_rows = [
            {
                "key": _source_relationship_key(dataset_id, relationship),
                "id": _source_relationship_key(dataset_id, relationship),
                "dataset_id": dataset_id,
                "source": _key(dataset_id, relationship.source_id),
                "target": _key(dataset_id, relationship.target_id),
                "relation_type": relationship.type,
                "weight": relationship.weight,
                "timestamp": relationship.timestamp.isoformat() if relationship.timestamp else None,
                "source_doc": relationship.source_doc,
            }
            for relationship in relationships
        ]
        entity_query = """
        UNWIND $rows AS row
        MERGE (entity:Entity {key: row.key})
        ON CREATE SET entity.id = row.id, entity.dataset_id = row.dataset_id,
            entity.entity_type = row.entity_type, entity.display_name = row.display_name,
            entity.identifiers_json = row.identifiers_json, entity.attributes_json = row.attributes_json,
            entity.filter_values = row.filter_values, entity.aliases = row.aliases,
            entity.source_docs = row.source_docs
        ON MATCH SET entity.display_name = coalesce(entity.display_name, row.display_name),
            entity.attributes_json = CASE WHEN row.attributes_json = '{}' THEN entity.attributes_json ELSE row.attributes_json END,
            entity.aliases = reduce(values = coalesce(entity.aliases, []), item IN row.aliases |
                CASE WHEN item IN values THEN values ELSE values + item END),
            entity.source_docs = reduce(values = coalesce(entity.source_docs, []), item IN row.source_docs |
                CASE WHEN item IN values THEN values ELSE values + item END)
        """
        relation_query = """
        UNWIND $rows AS row
        MATCH (source:Entity {key: row.source}), (target:Entity {key: row.target})
        MERGE (relation:Relation {key: row.key})
        ON CREATE SET relation.id = row.id, relation.dataset_id = row.dataset_id,
            relation.relation_type = row.relation_type, relation.weight = row.weight,
            relation.timestamp = row.timestamp, relation.source_docs = [row.source_doc],
            relation.attributes_json = '{}', relation.derived = false
        ON MATCH SET relation.weight = row.weight,
            relation.source_docs = CASE WHEN row.source_doc IN coalesce(relation.source_docs, [])
                THEN relation.source_docs ELSE coalesce(relation.source_docs, []) + row.source_doc END
        MERGE (source)-[:SOURCE]->(relation)
        MERGE (relation)-[:TARGET]->(target)
        """
        with self.driver.session() as session:
            def write(tx: Any) -> None:
                for rows in _chunks(entity_rows, batch_size):
                    tx.run(entity_query, rows=rows).consume()
                for rows in _chunks(relation_rows, batch_size):
                    tx.run(relation_query, rows=rows).consume()
                tx.run("MATCH (d:Dataset {id: $id}) SET d.version = d.version + 1", id=dataset_id).consume()
            session.execute_write(write)
        return {"entities": len(entities), "relationships": len(relationships), "graph_version": self.get_dataset(dataset_id).version}

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

    def query(self, intent: Any) -> Any:
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
        if intent.intent == "full_graph":
            return self._person_graph_for_ids(intent.dataset_id, None)
        if intent.intent == "cluster_graph":
            if not intent.cluster_id:
                raise ValueError("cluster_id is required for cluster_graph")
            return self.cluster_graph(intent.dataset_id, intent.cluster_id)
        if intent.intent == "list_clusters":
            return self.list_clusters(intent.dataset_id, intent.limit)
        if intent.intent == "entity_details":
            if not intent.entity_id:
                raise ValueError("entity_id is required for entity_details")
            return self.entity_details(intent.dataset_id, intent.entity_id)
        if intent.intent == "search_entities":
            if not intent.query:
                raise ValueError("query is required for search_entities")
            return self.search_entities(intent.dataset_id, intent.query, intent.entity_type, intent.limit)
        if intent.intent == "statistics":
            return self.statistics(intent.dataset_id)
        raise ValueError("unsupported query intent")

    def _find_entities(self, intent: Any) -> list[dict[str, Any]]:
        clauses, parameters = [], {"dataset_id": intent.dataset_id, "entity_type": intent.entity_type, "limit": intent.limit}
        for index, filter_item in enumerate(intent.filters):
            key = f"filter_{index}"
            prefix = f"{filter_item.field}"
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
        # Emitted in both directions so the Louvain projection is undirected: a node that is only
        # ever a relation TARGET must still contribute to community membership. This only affects
        # the in-memory GDS graph built for clustering — the underlying :SOURCE/:TARGET relationships
        # in the database stay directed and untouched.
        relation_query = (
            "MATCH (source:Entity {dataset_id: $dataset_id})-[:SOURCE]->(:Relation)-[:TARGET]->(target:Entity {dataset_id: $dataset_id}) "
            "RETURN id(source) AS source, id(target) AS target "
            "UNION "
            "MATCH (source:Entity {dataset_id: $dataset_id})-[:SOURCE]->(:Relation)-[:TARGET]->(target:Entity {dataset_id: $dataset_id}) "
            "RETURN id(target) AS source, id(source) AS target"
        )
        return self._run_louvain(name, dataset_id, node_query, relation_query, limit)

    def _person_communities(self, dataset_id: str, limit: int) -> list[list[str]]:
        """Louvain over the PERSON-only projection: direct CALLED pairs plus account-derived
        FINANCIAL_LINK pairs (see _person_graph_for_ids), each undirected for clustering purposes."""
        name = f"community_person_{dataset_id.replace('-', '_')}"
        node_query = "MATCH (entity:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'}) RETURN id(entity) AS id"
        relation_query = (
            "MATCH (source:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'CALLED'})-[:TARGET]->(target:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'}) "
            "RETURN id(source) AS source, id(target) AS target "
            "UNION "
            "MATCH (source:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'CALLED'})-[:TARGET]->(target:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'}) "
            "RETURN id(target) AS source, id(source) AS target "
            "UNION "
            "MATCH (source:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(sa:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
            "MATCH (sa)-[:SOURCE]->(:Relation {relation_type: 'TRANSFERRED_TO'})-[:TARGET]->(ta:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
            "MATCH (target:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(ta) "
            "WHERE source <> target "
            "RETURN id(source) AS source, id(target) AS target "
            "UNION "
            "MATCH (source:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(sa:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
            "MATCH (sa)-[:SOURCE]->(:Relation {relation_type: 'TRANSFERRED_TO'})-[:TARGET]->(ta:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
            "MATCH (target:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(ta) "
            "WHERE source <> target "
            "RETURN id(target) AS source, id(source) AS target"
        )
        return self._run_louvain(name, dataset_id, node_query, relation_query, limit)

    def _run_louvain(self, name_prefix: str, dataset_id: str, node_query: str, relation_query: str, limit: int) -> list[list[str]]:
        # Unique per call: concurrent requests (e.g. two browser tabs, or React
        # StrictMode's double effect-invocation in dev) must not collide on GDS's
        # global in-memory graph name registry.
        name = f"{name_prefix}_{uuid.uuid4().hex}"
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

    # -- Cytoscape-ready graph responses -------------------------------------------------

    def cluster_graph(self, dataset_id: str, cluster_id: str) -> dict[str, Any]:
        communities = self._person_communities(dataset_id, limit=1_000_000)
        index = _cluster_index(cluster_id)
        if index is None or index < 0 or index >= len(communities):
            raise KeyError("cluster not found")
        members = communities[index]
        graph = self._person_graph_for_ids(dataset_id, members)
        graph["cluster_id"] = cluster_id
        graph["entity_count"] = len(members)
        graph["link_count"] = graph["edge_count"]
        return graph

    def list_clusters(self, dataset_id: str, limit: int) -> list[dict[str, Any]]:
        communities = self._person_communities(dataset_id, limit=1_000_000)
        clusters = []
        for index, members in enumerate(communities[:limit]):
            graph = self._person_graph_for_ids(dataset_id, members)
            clusters.append({"cluster_id": str(index), "entity_count": len(members), "link_count": graph["edge_count"]})
        return clusters

    def _person_graph_for_ids(self, dataset_id: str, entity_ids: list[str] | None) -> dict[str, Any]:
        """PERSON-only Cytoscape graph: direct CALLED person-to-person edges, plus derived
        FINANCIAL_LINK edges for person pairs whose owned accounts transacted with each other.
        PHONE/ACCOUNT entities never appear as nodes here — they remain reachable via entity_details."""
        with self.driver.session() as session:
            if entity_ids is None:
                node_rows = session.run("MATCH (e:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'}) RETURN e", dataset_id=dataset_id)
            else:
                node_rows = session.run("MATCH (e:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'}) WHERE e.id IN $ids RETURN e", dataset_id=dataset_id, ids=entity_ids)
            nodes = [_cytoscape_node(row["e"]) for row in node_rows]
            node_id_set = {node["data"]["id"] for node in nodes}

            called_rows = list(session.run(
                "MATCH (s:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(r:Relation {relation_type: 'CALLED'})-[:TARGET]->(t:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'}) "
                "OPTIONAL MATCH (r)<-[:SUPPORTS]-(ev:Evidence) "
                "RETURN r.id AS id, s.id AS source, t.id AS target, r.weight AS weight, collect(DISTINCT ev.id) AS evidence_ids",
                dataset_id=dataset_id,
            ))
            financial_rows = list(session.run(
                "MATCH (ps:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(sa:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
                "MATCH (sa)-[:SOURCE]->(r:Relation {relation_type: 'TRANSFERRED_TO'})-[:TARGET]->(ta:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
                "MATCH (pt:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(ta) "
                "WHERE ps <> pt "
                "OPTIONAL MATCH (r)<-[:SUPPORTS]-(ev:Evidence) "
                "RETURN r.id AS id, ps.id AS source, pt.id AS target, r.weight AS weight, sa.id AS source_account, ta.id AS target_account, collect(DISTINCT ev.id) AS evidence_ids",
                dataset_id=dataset_id,
            ))

        edges_by_pair: dict[frozenset, dict[str, Any]] = {}

        def add_relation(source: str, target: str, relation: dict[str, Any]) -> None:
            if entity_ids is not None and (source not in node_id_set or target not in node_id_set):
                return
            key = frozenset((source, target))
            edge = edges_by_pair.setdefault(key, {"source": source, "target": target, "relations": []})
            edge["relations"].append(relation)

        for row in called_rows:
            add_relation(row["source"], row["target"], {
                "relation_type": "CALLED",
                "relation_id": row["id"],
                "weight": row["weight"],
                "evidence_ids": [value for value in row["evidence_ids"] if value],
            })
        for row in financial_rows:
            add_relation(row["source"], row["target"], {
                "relation_type": "FINANCIAL_LINK",
                "relation_id": row["id"],
                "weight": row["weight"],
                "evidence_ids": [value for value in row["evidence_ids"] if value],
                "source_account": row["source_account"],
                "target_account": row["target_account"],
            })

        edges = [
            {
                "data": {
                    "id": f"{edge['source']}~{edge['target']}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "relation_types": sorted({relation["relation_type"] for relation in edge["relations"]}),
                    "relations": edge["relations"],
                }
            }
            for edge in edges_by_pair.values()
        ]
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    def entity_details(self, dataset_id: str, entity_id: str) -> dict[str, Any]:
        entity = self.entity(dataset_id, entity_id)
        relationships = self._relationships_for_entity(dataset_id, entity_id)
        relationships += self._financial_links_for_entity(dataset_id, entity_id)
        entity["relationships"] = relationships
        return entity

    def _relationships_for_entity(self, dataset_id: str, entity_id: str) -> list[dict[str, Any]]:
        query = """
        MATCH (e:Entity {key: $key})-[:SOURCE]->(r:Relation)-[:TARGET]->(target:Entity {dataset_id: $dataset_id})
        OPTIONAL MATCH (r)<-[:SUPPORTS]-(ev:Evidence)
        WITH r, target, 'outgoing' AS direction, collect(DISTINCT ev.id) AS evidence_ids, collect(DISTINCT ev.occurred_at) AS occurred_ats
        RETURN r.relation_type AS relation_type, r.weight AS weight, target, evidence_ids, occurred_ats, direction
        UNION
        MATCH (target:Entity {dataset_id: $dataset_id})-[:SOURCE]->(r:Relation)-[:TARGET]->(e:Entity {key: $key})
        OPTIONAL MATCH (r)<-[:SUPPORTS]-(ev:Evidence)
        WITH r, target, 'incoming' AS direction, collect(DISTINCT ev.id) AS evidence_ids, collect(DISTINCT ev.occurred_at) AS occurred_ats
        RETURN r.relation_type AS relation_type, r.weight AS weight, target, evidence_ids, occurred_ats, direction
        """
        with self.driver.session() as session:
            rows = session.run(query, key=_key(dataset_id, entity_id), dataset_id=dataset_id)
            results = []
            for row in rows:
                target = dict(row["target"])
                occurred_ats = [value for value in row["occurred_ats"] if value]
                evidence_ids = [value for value in row["evidence_ids"] if value]
                results.append({
                    "target": {
                        "id": target.get("id"),
                        "entity_type": target.get("entity_type"),
                        "display_name": target.get("display_name"),
                    },
                    "relation_type": row["relation_type"],
                    "weight": row["weight"],
                    "timestamp": occurred_ats[0] if occurred_ats else None,
                    "evidence_ids": evidence_ids,
                    "direction": row["direction"],
                })
            return results

    def _financial_links_for_entity(self, dataset_id: str, entity_id: str) -> list[dict[str, Any]]:
        """Derived PERSON-to-PERSON FINANCIAL_LINK connections via
        OWNS -> ACCOUNT -> TRANSFERRED_TO -> ACCOUNT -> OWNS (the same chain
        _person_graph_for_ids uses for the graph/cluster view). Multiple
        underlying transactions with the same connected person are merged
        into a single connection — each transaction is preserved verbatim
        under "transactions" rather than being dropped.
        """
        query = (
            "MATCH (ps:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(sa:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
            "MATCH (sa)-[:SOURCE]->(r:Relation {relation_type: 'TRANSFERRED_TO'})-[:TARGET]->(ta:Entity {entity_type: 'ACCOUNT', dataset_id: $dataset_id}) "
            "MATCH (pt:Entity {dataset_id: $dataset_id, entity_type: 'PERSON'})-[:SOURCE]->(:Relation {relation_type: 'OWNS'})-[:TARGET]->(ta) "
            "WHERE ps <> pt AND (ps.id = $entity_id OR pt.id = $entity_id) "
            "OPTIONAL MATCH (r)<-[:SUPPORTS]-(ev:Evidence) "
            "RETURN ps.id AS source_person, ps.display_name AS source_name, "
            "pt.id AS target_person, pt.display_name AS target_name, "
            "r.id AS relation_id, r.weight AS weight, sa.id AS source_account, ta.id AS target_account, "
            "collect(DISTINCT ev.id) AS evidence_ids, collect(DISTINCT ev.occurred_at) AS occurred_ats"
        )
        with self.driver.session() as session:
            rows = list(session.run(query, dataset_id=dataset_id, entity_id=entity_id))

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            is_source = row["source_person"] == entity_id
            other_id = row["target_person"] if is_source else row["source_person"]
            other_name = row["target_name"] if is_source else row["source_name"]
            occurred_ats = [value for value in row["occurred_ats"] if value]
            evidence_ids = [value for value in row["evidence_ids"] if value]
            transaction_timestamp = occurred_ats[0] if occurred_ats else None

            entry = grouped.setdefault(other_id, {
                "target": {"id": other_id, "entity_type": "PERSON", "display_name": other_name},
                "relation_type": "FINANCIAL_LINK",
                "weight": 0.0,
                "timestamp": None,
                "evidence_ids": [],
                "direction": "derived",
                "transactions": [],
            })
            entry["weight"] += row["weight"] or 0.0
            entry["evidence_ids"].extend(evidence_ids)
            entry["transactions"].append({
                "relation_id": row["relation_id"],
                "weight": row["weight"],
                "source_account": row["source_account"],
                "target_account": row["target_account"],
                "timestamp": transaction_timestamp,
                "evidence_ids": evidence_ids,
            })
            if transaction_timestamp and (entry["timestamp"] is None or transaction_timestamp > entry["timestamp"]):
                entry["timestamp"] = transaction_timestamp

        for entry in grouped.values():
            entry["evidence_ids"] = list(dict.fromkeys(entry["evidence_ids"]))

        return list(grouped.values())

    def search_entities(self, dataset_id: str, query: str, entity_type: str | None, limit: int) -> list[dict[str, Any]]:
        cypher = (
            "MATCH (e:Entity {dataset_id: $dataset_id}) "
            "WHERE ($entity_type IS NULL OR e.entity_type = $entity_type) AND ("
            "toLower(e.id) CONTAINS toLower($q) "
            "OR toLower(coalesce(e.display_name, '')) CONTAINS toLower($q) "
            "OR toLower(e.attributes_json) CONTAINS toLower($q)"
            ") RETURN e ORDER BY e.id LIMIT $limit"
        )
        with self.driver.session() as session:
            rows = session.run(cypher, dataset_id=dataset_id, entity_type=entity_type, q=query, limit=limit)
            return [_cytoscape_node(row["e"])["data"] for row in rows]

    def statistics(self, dataset_id: str) -> dict[str, Any]:
        graph = self._person_graph_for_ids(dataset_id, None)
        total_entities = graph["node_count"]
        total_relationships = graph["edge_count"]
        total_clusters = len(self._person_communities(dataset_id, limit=1_000_000))
        avg_degree = round((2 * total_relationships / total_entities), 3) if total_entities else 0.0
        avg_degree_separation = _average_path_length(graph)
        return {
            "total_entities": total_entities,
            "total_relationships": total_relationships,
            "total_clusters": total_clusters,
            "avg_degree": avg_degree,
            "avg_degree_separation": avg_degree_separation,
        }


def _cytoscape_node(node: Any) -> dict[str, Any]:
    value = dict(node)
    attributes = json.loads(value.get("attributes_json") or "{}")
    identifiers = json.loads(value.get("identifiers_json") or "{}")
    return {
        "data": {
            "id": value.get("id"),
            "label": value.get("display_name") or value.get("id"),
            "entity_type": value.get("entity_type"),
            "display_name": value.get("display_name"),
            "attributes": attributes,
            "identifiers": identifiers,
        }
    }


def _cluster_index(cluster_id: str) -> int | None:
    try:
        return int(cluster_id)
    except (TypeError, ValueError):
        return None


def _average_path_length(graph: dict[str, Any]) -> float:
    """Exact average shortest-path length (in hops) over every reachable pair.

    The PERSON-only graph is small (hundreds of nodes/edges), so a BFS from every
    node is cheap and gives an exact figure instead of the sampled approximation
    a large graph would need.
    """
    adjacency: dict[str, set[str]] = {node["data"]["id"]: set() for node in graph["nodes"]}
    for edge in graph["edges"]:
        source, target = edge["data"]["source"], edge["data"]["target"]
        adjacency[source].add(target)
        adjacency[target].add(source)

    total_distance = 0
    pair_count = 0
    for start in adjacency:
        distances = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in adjacency[node]:
                if neighbor not in distances:
                    distances[neighbor] = distances[node] + 1
                    queue.append(neighbor)
        for node, distance in distances.items():
            if node != start:
                total_distance += distance
                pair_count += 1

    if pair_count == 0:
        return 0.0
    return round(total_distance / pair_count, 3)


def _filter_values(entity: EntityInput) -> list[str]:
    values = {"id": entity.id} | entity.attributes | entity.identifiers | ({"display_name": entity.display_name} if entity.display_name is not None else {})
    return [f"{field}{json.dumps(value, sort_keys=True)}" for field, value in values.items()]


def _batch_filter_values(entity: SourceEntity) -> list[str]:
    values = [f"id{json.dumps(entity.id)}"]
    if entity.canonical_name:
        values.append(f"display_name{json.dumps(entity.canonical_name)}")
    return values


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


def _source_relationship_key(dataset_id: str, relationship: SourceRelationship) -> str:
    identity = "|".join((dataset_id, relationship.type, relationship.source_id, relationship.target_id, relationship.timestamp.isoformat() if relationship.timestamp else ""))
    return f"{dataset_id}:source:{hashlib.sha256(identity.encode()).hexdigest()}"


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]
