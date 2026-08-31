// Base URL is configurable via VITE_API_BASE_URL; it defaults to '' (relative),
// which relies on the Vite dev server proxy in vite.config.js for local dev.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export const DATASET_ID = import.meta.env.VITE_DATASET_ID ?? 'case-cyb-2026-001'

/** Posts one intent to the generic /api/query endpoint and returns its `results`. */
export async function queryApi(intent) {
  let response
  try {
    response = await fetch(`${API_BASE}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(intent),
    })
  } catch {
    throw new Error('Unable to reach the API server.')
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed (${response.status})`)
  }
  return body.results
}
