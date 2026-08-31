// Restrained, muted palette for PERSON nodes — deliberately not green, so the
// accent color stays reserved for selection/UI state.
const PERSON_COLORS = ['#5c7fa3', '#8a7ab8', '#c9a15a', '#4f9e93', '#b5697a', '#7a8699']

function hashString(value) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index)
    hash |= 0
  }
  return hash
}

/** Deterministic muted color for a node id, stable across graph/cluster views. */
export function colorForId(id) {
  return PERSON_COLORS[Math.abs(hashString(id)) % PERSON_COLORS.length]
}
