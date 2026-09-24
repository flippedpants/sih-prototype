import { apiFetch } from './client'

// GET /cases/{case_id}/overview — app/api/main.py:case_overview
// Returns null when the backend reports 404 ("Case not found").
export async function fetchCaseOverview(caseId) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/overview`)

  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`Failed to load case overview (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/summary — app/api/main.py:case_summary
// Returns null when the backend reports 404 ("Case summary not found") —
// this is the normal/expected state for any case without a generated
// summary yet, not an error.
export async function fetchCaseSummary(caseId) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/summary`)

  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`Failed to load case summary (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/graph — app/api/main.py:case_graph
// Note: unlike /overview, this endpoint returns 200 with empty nodes/edges
// for a case that doesn't exist — it never 404s.
// `filter`/`cutoff` are omitted by default (full, unfiltered graph); pass
// them only in response to an explicit user action, never on initial load.
export async function fetchCaseGraph(caseId, { filter, cutoff } = {}) {
  const params = new URLSearchParams()
  if (filter) params.set('filter', filter)
  if (cutoff !== undefined && cutoff !== null) params.set('cutoff', String(cutoff))
  const query = params.toString()

  const response = await apiFetch(
    `/cases/${encodeURIComponent(caseId)}/graph${query ? `?${query}` : ''}`
  )

  if (!response.ok) {
    throw new Error(`Failed to load case graph (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/nodes/top — app/api/main.py:top_nodes
// Used by the Key Players ranking panel. `limit` defaults to the backend's
// own default (10) — pass it explicitly only if a caller ever needs more.
export async function fetchTopNodes(caseId, { metric = 'betweenness', limit } = {}) {
  const params = new URLSearchParams({ metric })
  if (limit !== undefined && limit !== null) params.set('limit', String(limit))

  const response = await apiFetch(
    `/cases/${encodeURIComponent(caseId)}/nodes/top?${params.toString()}`
  )

  if (!response.ok) {
    throw new Error(`Failed to load top nodes (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/nodes/{node_id} — app/api/main.py:node_detail
// Returns null when the backend reports 404 ("Node not found in case").
export async function fetchNodeDetail(caseId, nodeId) {
  const response = await apiFetch(
    `/cases/${encodeURIComponent(caseId)}/nodes/${encodeURIComponent(nodeId)}`
  )

  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`Failed to load node detail (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/communities — app/api/main.py:communities
export async function fetchCommunities(caseId) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/communities`)

  if (!response.ok) {
    throw new Error(`Failed to load communities (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/communities/{community_id} — app/api/main.py:community_detail
// Returns null when the backend reports 404 ("Community not found in case").
export async function fetchCommunityDetail(caseId, communityId) {
  const response = await apiFetch(
    `/cases/${encodeURIComponent(caseId)}/communities/${encodeURIComponent(communityId)}`
  )

  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`Failed to load community detail (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/path — app/api/main.py:path
// Never 404s: an unreachable pair (or an id that doesn't resolve in this
// case) comes back as a normal 200 with path_found: false.
export async function fetchPath(caseId, fromNodeId, toNodeId) {
  const params = new URLSearchParams({ from_node_id: fromNodeId, to_node_id: toNodeId })
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/path?${params.toString()}`)

  if (!response.ok) {
    throw new Error(`Failed to trace path (HTTP ${response.status})`)
  }

  return response.json()
}

// GET /cases/{case_id}/criticality — app/api/main.py:criticality
// The endpoint never runs a live simulation ("Slice precomputed
// CriticalityRank nodes"); top_k must be one of 3, 6, or 10.
export async function fetchCriticality(caseId, topK = 6) {
  const params = new URLSearchParams({ top_k: String(topK) })
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/criticality?${params.toString()}`)

  if (!response.ok) {
    throw new Error(`Failed to load criticality data (HTTP ${response.status})`)
  }

  return response.json()
}
