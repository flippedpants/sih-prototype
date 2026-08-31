import { useEffect, useRef, useState } from 'react'
import { searchPersons } from '../api/entities.js'
import './EntitySearch.css'

const DEBOUNCE_MS = 250

function EntitySearch({ onSelectEntity }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const rootRef = useRef(null)
  const requestIdRef = useRef(0)

  useEffect(() => {
    function handleClickOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    const trimmed = query.trim()
    if (!trimmed) {
      setResults([])
      setLoading(false)
      setError(null)
      return undefined
    }

    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setLoading(true)
    setError(null)

    const timeout = setTimeout(() => {
      searchPersons(trimmed)
        .then((found) => {
          if (requestIdRef.current !== requestId) return
          setResults(found)
          setLoading(false)
        })
        .catch((requestError) => {
          if (requestIdRef.current !== requestId) return
          setError(requestError.message)
          setLoading(false)
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(timeout)
  }, [query])

  function handleChange(event) {
    setQuery(event.target.value)
    setOpen(true)
  }

  function handleSelect(entity) {
    onSelectEntity(entity.id)
    setQuery(entity.displayName || entity.id)
    setOpen(false)
  }

  function handleKeyDown(event) {
    if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const trimmed = query.trim()

  return (
    <div className="entity-search" ref={rootRef}>
      <div className="entity-search-field">
        <span className="entity-search-icon">🔍</span>
        <input
          type="text"
          value={query}
          onChange={handleChange}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search by name or ID..."
        />
      </div>

      {open && trimmed && (
        <div className="entity-search-panel">
          {loading ? (
            <p className="entity-search-empty">Searching…</p>
          ) : error ? (
            <p className="entity-search-empty">Search failed: {error}</p>
          ) : results.length === 0 ? (
            <p className="entity-search-empty">No matches for &quot;{trimmed}&quot;</p>
          ) : (
            <ul className="entity-search-list" role="listbox">
              {results.map((entity) => (
                <li key={entity.id}>
                  <button
                    type="button"
                    className="entity-search-option"
                    onClick={() => handleSelect(entity)}
                  >
                    <span className="entity-search-option-name">
                      {entity.displayName || entity.id}
                    </span>
                    <span className="entity-search-option-meta">Person · {entity.id}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default EntitySearch
