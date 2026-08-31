import { queryApi, DATASET_ID } from './client.js'

function toPersonSummary(raw) {
  return {
    id: raw.id,
    type: raw.entity_type,
    displayName: raw.display_name || raw.id,
  }
}

/** Searches PERSON entities by name/ID via the real search_entities intent. */
export async function searchPersons(query, limit = 8) {
  const raw = await queryApi({
    intent: 'search_entities',
    dataset_id: DATASET_ID,
    entity_type: 'PERSON',
    query,
    limit,
  })
  return raw.map(toPersonSummary)
}

function toPersonDetails(raw) {
  const relationships = raw.relationships || []
  const knownLinks = relationships
    .filter((item) => item.target.entity_type === 'PHONE' || item.target.entity_type === 'ACCOUNT')
    .map((item) => ({
      id: item.target.id,
      type: item.target.entity_type,
      label: item.target.display_name || item.target.id,
    }))
  const connections = relationships
    .filter((item) => item.target.entity_type === 'PERSON')
    .map((item) => ({
      id: item.target.id,
      displayName: item.target.display_name || item.target.id,
      type: 'PERSON',
      relation: item.relation_type,
    }))

  return {
    id: raw.id,
    type: raw.entity_type,
    displayName: raw.display_name || raw.id,
    aliases: raw.aliases || [],
    attributes: raw.attributes || {},
    knownLinks,
    connections,
  }
}

/** Full entity details (attributes + known Phone/Account links + connected people) via entity_details. */
export async function fetchEntityDetails(entityId) {
  const raw = await queryApi({
    intent: 'entity_details',
    dataset_id: DATASET_ID,
    entity_id: entityId,
  })
  return toPersonDetails(raw)
}
