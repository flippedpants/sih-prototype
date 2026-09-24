import { apiFetch } from './client.js'

// GET /cases?filter=&sort= — see app/api/main.py:list_cases
export async function fetchCases({ filter, sort = 'last_activity' } = {}) {
  const params = new URLSearchParams()
  if (filter) params.set('filter', filter)
  if (sort) params.set('sort', sort)
  const query = params.toString()

  const response = await apiFetch(`/cases${query ? `?${query}` : ''}`)

  if (!response.ok) {
    throw new Error(`Failed to load cases (HTTP ${response.status})`)
  }

  return response.json()
}

export async function updateCase(caseId, fields) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  })

  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`Failed to save case (HTTP ${response.status})`)
  }

  return response.json()
}

export async function completeCase(caseId) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/complete`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`Failed to mark case completed (HTTP ${response.status})`)
  }
  return response.json()
}

export async function restoreCase(caseId) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}/restore`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`Failed to restore case (HTTP ${response.status})`)
  }
  return response.json()
}

export function caseCreatePayload({ name, priority, jurisdiction, summary }) {
  return {
    case_name: name,
    priority,
    jurisdiction,
    summary: summary || null,
  }
}

export function createCaseErrorMessage(status, detail) {
  if (status === 401) return 'Session expired. Sign in again.'
  if (status === 403) return 'Only administrators can create cases.'
  if (status === 409) return 'A conflicting case already exists.'
  if (status === 422) {
    if (typeof detail === 'string' && detail.trim()) return detail
    return 'Case name is required.'
  }
  return 'Unable to create case. Try again.'
}

export async function createCase(fields) {
  const response = await apiFetch('/cases', {
    method: 'POST',
    body: JSON.stringify(caseCreatePayload(fields)),
  })
  if (!response.ok) {
    let detail
    try {
      detail = (await response.json())?.detail
    } catch {
      detail = null
    }
    throw new Error(createCaseErrorMessage(response.status, detail))
  }
  return response.json()
}

export async function deleteCase(caseId) {
  const response = await apiFetch(`/cases/${encodeURIComponent(caseId)}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete case (HTTP ${response.status})`)
  }
}
