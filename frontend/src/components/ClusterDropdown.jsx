import { useEffect, useRef, useState } from 'react'
import './ClusterDropdown.css'

function ClusterDropdown({ clusters, selectedId, onSelect }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef(null)
  const inputRef = useRef(null)

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
    if (open) {
      inputRef.current?.focus()
    }
  }, [open])

  function toggleOpen() {
    if (!open) {
      setQuery('')
    }
    setOpen((prev) => !prev)
  }

  const selected = clusters.find((cluster) => cluster.id === selectedId)
  const isAllSelected = selectedId === 'all'
  const filtered = clusters.filter((cluster) =>
    cluster.name.toLowerCase().includes(query.trim().toLowerCase()),
  )

  function handleSelect(cluster) {
    onSelect(cluster.id)
    setOpen(false)
  }

  function handleSelectAll() {
    onSelect('all')
    setOpen(false)
  }

  function handleTriggerKeyDown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleOpen()
    }
  }

  function handlePanelKeyDown(event) {
    if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="cluster-dropdown" ref={rootRef}>
      <button
        type="button"
        className="cluster-dropdown-trigger"
        onClick={toggleOpen}
        onKeyDown={handleTriggerKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span
          className={
            selected || isAllSelected ? 'cluster-dropdown-value' : 'cluster-dropdown-placeholder'
          }
        >
          {isAllSelected ? 'All Network' : selected ? selected.name : 'Select cluster'}
        </span>
        <span className="cluster-dropdown-chevron">▼</span>
      </button>

      {open && (
        <div className="cluster-dropdown-panel" onKeyDown={handlePanelKeyDown}>
          <div className="cluster-dropdown-search">
            <span className="cluster-dropdown-search-icon">🔍</span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search clusters..."
            />
          </div>
          <button
            type="button"
            role="option"
            aria-selected={isAllSelected}
            className={
              isAllSelected
                ? 'cluster-dropdown-option cluster-dropdown-option-all cluster-dropdown-option-active'
                : 'cluster-dropdown-option cluster-dropdown-option-all'
            }
            onClick={handleSelectAll}
          >
            <span className="cluster-dropdown-option-name">All Network</span>
            <span className="cluster-dropdown-option-meta">Show the complete network</span>
          </button>
          <div className="cluster-dropdown-divider" />
          <ul className="cluster-dropdown-list" role="listbox">
            {filtered.length === 0 && (
              <li className="cluster-dropdown-empty">No clusters match &quot;{query}&quot;</li>
            )}
            {filtered.map((cluster) => (
              <li key={cluster.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={cluster.id === selectedId}
                  className={
                    cluster.id === selectedId
                      ? 'cluster-dropdown-option cluster-dropdown-option-active'
                      : 'cluster-dropdown-option'
                  }
                  onClick={() => handleSelect(cluster)}
                >
                  <span className="cluster-dropdown-option-name">{cluster.name}</span>
                  <span className="cluster-dropdown-option-meta">
                    {cluster.entities} entities · {cluster.links} links
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default ClusterDropdown
