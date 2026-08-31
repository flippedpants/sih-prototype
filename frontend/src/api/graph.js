import { queryApi, DATASET_ID } from './client.js'
import { colorForId } from '../utils/personColor.js'

function toElements(rawGraph) {
  const nodes = rawGraph.nodes.map((node) => ({
    data: {
      id: node.data.id,
      label: node.data.display_name || node.data.id,
      kind: 'PERSON',
      color: colorForId(node.data.id),
    },
  }))
  const edges = rawGraph.edges.map((edge) => ({
    data: {
      id: edge.data.id,
      source: edge.data.source,
      target: edge.data.target,
      kind: edge.data.relation_types[0],
    },
  }))
  return [...nodes, ...edges]
}

function buildGraphResult(clusterId, rawGraph) {
  return {
    clusterId,
    elements: toElements(rawGraph),
  }
}

/** The complete PERSON-only network — used for the default "All Network" view. */
export async function fetchFullGraph() {
  const raw = await queryApi({ intent: 'full_graph', dataset_id: DATASET_ID })
  return buildGraphResult('all', raw)
}

/** The PERSON-only subgraph for one Louvain cluster id. */
export async function fetchClusterGraph(clusterId) {
  const raw = await queryApi({ intent: 'cluster_graph', dataset_id: DATASET_ID, cluster_id: clusterId })
  return buildGraphResult(clusterId, raw)
}

/** Non-singleton clusters only — singleton communities are "Unclustered", not
 * individually selectable clusters. */
export async function fetchListClusters() {
  const raw = await queryApi({ intent: 'list_clusters', dataset_id: DATASET_ID, limit: 100 })
  return raw
    .filter((cluster) => cluster.entity_count > 1)
    .map((cluster) => ({
      id: cluster.cluster_id,
      name: `Cluster ${cluster.cluster_id}`,
      entities: cluster.entity_count,
      links: cluster.link_count,
    }))
}
