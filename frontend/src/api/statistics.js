import { queryApi, DATASET_ID } from './client.js'

/** PERSON-only graph statistics (see backend statistics()), formatted for StatsBar. */
export async function fetchStatistics() {
  const raw = await queryApi({ intent: 'statistics', dataset_id: DATASET_ID })
  return [
    { label: 'Total entities', value: raw.total_entities.toLocaleString() },
    { label: 'Total relationships', value: raw.total_relationships.toLocaleString() },
    { label: 'Total clusters', value: raw.total_clusters.toLocaleString() },
    { label: 'Avg degree', value: raw.avg_degree.toFixed(2) },
    { label: 'Avg degree separation', value: raw.avg_degree_separation.toFixed(2) },
  ]
}
