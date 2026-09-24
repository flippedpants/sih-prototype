import { useEffect, useMemo, useRef, useState } from 'react'
import AppHeader from '../components/AppHeader'
import CreateCaseModal from '../components/CreateCaseModal'
import EditCaseModal from '../components/EditCaseModal'
import CaseAccessModal from '../components/CaseAccessModal'
import UserManagementModal from '../components/UserManagementModal'
import { useAuth } from '../auth/AuthContext'
import { casePermissions, visibleCaseCardActions, visibleCaseListActions } from '../auth/permissions'
import { completeCase, createCase, deleteCase, fetchCases, restoreCase } from '../api/casesApi'
import { HOME_PAGE } from '../nav/navigation'
import gridViewIcon from '../assets/cases/grid-view.svg'
import listViewIcon from '../assets/cases/list-view.svg'
import plusIcon from '../assets/cases/plus.svg'
import sortArrowIcon from '../assets/cases/sort-arrow.svg'
import topology1 from '../assets/cases/topology-1.svg'
import topology2 from '../assets/cases/topology-2.svg'
import topology3 from '../assets/cases/topology-3.svg'
import topology4 from '../assets/cases/topology-4.svg'
import topology5 from '../assets/cases/topology-5.svg'
import topology6 from '../assets/cases/topology-6.svg'
import './Cases.css'

const TOPOLOGIES = [topology1, topology2, topology3, topology4, topology5, topology6]

// Lower rank sorts first (most urgent). Cases with no priority sort last.
const PRIORITY_RANK = { I: 0, II: 1, III: 2, IV: 3 }
const SORT_OPTIONS = [
  { key: 'last_activity', label: 'Last Activity' },
  { key: 'name', label: 'Name' },
  { key: 'priority', label: 'Priority' },
]
const SORT_LABEL = Object.fromEntries(SORT_OPTIONS.map((o) => [o.key, `${o.label} ↓`]))

const TABS = [
  { key: 'all', label: 'All Cases' },
  { key: 'active', label: 'Active' },
  { key: 'archived', label: 'Completed' },
  { key: 'flagged', label: 'Important' },
]

function formatRelativeTime(iso) {
  if (!iso) return 'N/A'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'N/A'

  const diffMs = Date.now() - date.getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  const weeks = Math.floor(days / 7)
  return `${weeks}w ago`
}

// Maps a GET /cases row (app/api/models.py:CaseSummary) onto the card's display shape.
// Backend statuses are ACTIVE/IMPORTANT/COMPLETED; `archived`/`statusClass` keep the
// completed-case styling hook (`case-card--archived`, `case-card__status--archived`)
// while the badge text itself reads "COMPLETED".
function mapCaseToCard(apiCase, index) {
  const isCompleted = (apiCase.status || '').toLowerCase() === 'completed'

  return {
    id: apiCase.case_id,
    archived: isCompleted,
    statusClass: isCompleted ? 'archived' : 'active',
    status: isCompleted ? 'COMPLETED' : 'ACTIVE',
    title: apiCase.name || apiCase.case_id,
    docket: `DOCKET // ${apiCase.case_id}${apiCase.priority ? ` · PRIORITY ${apiCase.priority}` : ''}`,
    description: apiCase.description || 'No description on file.',
    topology: TOPOLOGIES[index % TOPOLOGIES.length],
    nodes: String(apiCase.node_count ?? 0),
    edges: String(apiCase.edge_count ?? 0),
    updated: formatRelativeTime(apiCase.updated_at),
    lead: apiCase.lead_analyst || 'UNASSIGNED',
  }
}

function CaseCard({
  caseItem,
  starred,
  onToggleStar,
  onOpen,
  actions = [],
  onEdit,
  onManageAccess,
  onComplete,
  onRestore,
  onDelete,
}) {
  return (
    <article
      className={`case-card${caseItem.archived ? ' case-card--archived' : ''}`}
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen?.()
        }
      }}
    >
      <div className="case-card__body">
        <div className="case-card__badges">
          <span className={`case-card__status case-card__status--${caseItem.statusClass}`}>
            {caseItem.status}
          </span>
          <button
            type="button"
            className={`case-card__star${starred ? ' case-card__star--on' : ''}`}
            aria-label={starred ? 'Unstar case' : 'Star case'}
            aria-pressed={starred}
            onClick={(event) => {
              event.stopPropagation()
              onToggleStar?.()
            }}
            onKeyDown={(event) => event.stopPropagation()}
          >
            <svg viewBox="0 0 12 12" aria-hidden="true">
              <path
                d="M6 1.15 7.38 3.95l3.1.45-2.24 2.18.53 3.08L6 8.2l-2.77 1.46.53-3.08L1.52 4.4l3.1-.45L6 1.15z"
                fill={starred ? 'currentColor' : 'none'}
                stroke="currentColor"
                strokeWidth="1"
              />
            </svg>
          </button>
        </div>
        <div className="case-card__top">
          <div className="case-card__heading">
            <h2 className="case-card__title">{caseItem.title}</h2>
            <p className="case-card__docket">{caseItem.docket}</p>
          </div>
          <div className="case-card__topology">
            <img src={caseItem.topology} alt="" />
          </div>
        </div>

        <p className="case-card__summary">{caseItem.description}</p>
      </div>

      <div className="case-card__footer">
        <div className="case-card__stats">
          <div className="case-card__stat">
            <span className="case-card__stat-label">NODES</span>
            <span className="case-card__stat-value">{caseItem.nodes}</span>
          </div>
          <div className="case-card__stat">
            <span className="case-card__stat-label">EDGES</span>
            <span className="case-card__stat-value">{caseItem.edges}</span>
          </div>
          <div className="case-card__stat">
            <span className="case-card__stat-label">UPDATED</span>
            <span className="case-card__stat-value case-card__stat-value--plain">{caseItem.updated}</span>
          </div>
        </div>
        <div className="case-card__meta">
          <span>LEAD: {caseItem.lead}</span>
        </div>
        {actions.length > 0 && (
          <div className="case-card__actions">
            {actions.includes('editCaseMetadata') && (
              <button
                type="button"
                className="case-card__edit"
                onClick={(event) => {
                  event.stopPropagation()
                  onEdit?.()
                }}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Edit Case
              </button>
            )}
            {actions.includes('manageCaseAccess') && (
              <button
                type="button"
                className="case-card__edit"
                onClick={(event) => {
                  event.stopPropagation()
                  onManageAccess?.()
                }}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Manage Access
              </button>
            )}
            {actions.includes('archiveCase') && (
              <button
                type="button"
                className="case-card__edit"
                onClick={(event) => {
                  event.stopPropagation()
                  onComplete?.()
                }}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Completed
              </button>
            )}
            {actions.includes('restoreCase') && (
              <button
                type="button"
                className="case-card__edit"
                onClick={(event) => {
                  event.stopPropagation()
                  onRestore?.()
                }}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Restore
              </button>
            )}
            {actions.includes('deleteCase') && (
              <button
                type="button"
                className="case-card__edit"
                onClick={(event) => {
                  event.stopPropagation()
                  onDelete?.()
                }}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Delete
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  )
}

function Cases({
  onOpenCase,
  onNavigate,
  createdCases: createdCasesProp,
  onCreateCase,
  caseEdits = {},
  onUpdateCase,
  onCaseStatusChange,
  onCaseRemoved,
}) {
  const { role } = useAuth()
  const permissions = casePermissions(role)
  const canCreateCase = visibleCaseListActions(role).includes('createCase')
  const [sort, setSort] = useState('last_activity')
  const [sortOpen, setSortOpen] = useState(false)
  const sortRef = useRef(null)
  const [activeTab, setActiveTab] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [fetchedCases, setFetchedCases] = useState([])
  const [createdCasesLocal, setCreatedCasesLocal] = useState([])
  const [loadState, setLoadState] = useState('loading') // 'loading' | 'ready' | 'error'
  const [errorMessage, setErrorMessage] = useState(null)
  const [retryToken, setRetryToken] = useState(0)
  const [viewMode, setViewMode] = useState('grid')
  const [starredIds, setStarredIds] = useState(() => new Set())
  const [createOpen, setCreateOpen] = useState(false)
  const [editCase, setEditCase] = useState(null)
  const [accessCase, setAccessCase] = useState(null)
  const [usersOpen, setUsersOpen] = useState(false)
  const [successMessage, setSuccessMessage] = useState(null)
  const createdCases = permissions.createCase ? (createdCasesProp ?? createdCasesLocal) : []
  const canManageUsers = visibleCaseListActions(role).includes('manageUsers')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoadState('loading')
      setErrorMessage(null)
      try {
        // The backend only understands last_activity/name — "priority" is a
        // client-side-only sort applied to whatever it returns, below.
        const all = await fetchCases({ sort: sort === 'name' ? 'name' : 'last_activity' })
        if (cancelled) return
        setFetchedCases(all)
        setLoadState('ready')
      } catch (err) {
        if (cancelled) return
        setErrorMessage(err.message || 'Failed to load cases')
        setLoadState('error')
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [sort, retryToken])

  useEffect(() => {
    if (!successMessage) return undefined
    const timeoutId = window.setTimeout(() => setSuccessMessage(null), 4000)
    return () => window.clearTimeout(timeoutId)
  }, [successMessage])

  useEffect(() => {
    if (!sortOpen) return undefined
    const handleClickOutside = (event) => {
      if (sortRef.current && !sortRef.current.contains(event.target)) setSortOpen(false)
    }
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setSortOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [sortOpen])

  const allCases = useMemo(() => {
    const remoteIds = new Set(fetchedCases.map((c) => c.case_id))
    const local = createdCases.filter((c) => !remoteIds.has(c.case_id))
    const merged = [...local, ...fetchedCases].map((c) =>
      caseEdits[c.case_id] ? { ...c, ...caseEdits[c.case_id] } : c
    )
    if (sort === 'name') {
      return [...merged].sort((a, b) =>
        (a.name || a.case_id).localeCompare(b.name || b.case_id, undefined, { sensitivity: 'base' })
      )
    }
    if (sort === 'priority') {
      return [...merged].sort((a, b) => {
        const rankA = PRIORITY_RANK[a.priority] ?? Number.MAX_SAFE_INTEGER
        const rankB = PRIORITY_RANK[b.priority] ?? Number.MAX_SAFE_INTEGER
        if (rankA !== rankB) return rankA - rankB
        return (a.name || a.case_id).localeCompare(b.name || b.case_id, undefined, { sensitivity: 'base' })
      })
    }
    return merged
  }, [fetchedCases, createdCases, sort, caseEdits])

  const activeCases = useMemo(
    () => allCases.filter((c) => (c.status || '').toLowerCase() !== 'completed'),
    [allCases]
  )
  const archivedCases = useMemo(
    () => allCases.filter((c) => (c.status || '').toLowerCase() === 'completed'),
    [allCases]
  )
  const importantCases = useMemo(
    () => allCases.filter((c) => starredIds.has(c.case_id)),
    [allCases, starredIds]
  )

  const total = allCases.length
  const activeCount = activeCases.length
  const archivedCount = archivedCases.length
  const flaggedCount = importantCases.length

  const tabCases =
    activeTab === 'active'
      ? activeCases
      : activeTab === 'archived'
        ? archivedCases
        : activeTab === 'flagged'
          ? importantCases
          : allCases

  const trimmedQuery = searchQuery.trim().toLowerCase()
  const displayedCases = trimmedQuery
    ? tabCases.filter((c) => {
        const id = (c.case_id || '').toLowerCase()
        const name = (c.name || '').toLowerCase()
        return id.includes(trimmedQuery) || name.includes(trimmedQuery)
      })
    : tabCases

  const tabCounts = { all: total, active: activeCount, archived: archivedCount, flagged: flaggedCount }

  return (
    <div className="cases-page">
      <AppHeader
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onBrandClick={() => onNavigate?.(HOME_PAGE)}
      />

      <main className="cases-main">
        <div className="cases-toolbar">
          <div className="cases-toolbar__left">
            <div className="cases-heading">
              <h1>Cases</h1>
              <span className="cases-heading__badge">
                [ {total} TOTAL // {activeCount} ACTIVE ]
              </span>
            </div>
          </div>
          <div className="cases-toolbar__right">
            <div className="cases-view-switch">
              <button
                type="button"
                className={`cases-view-switch__btn${viewMode === 'grid' ? ' cases-view-switch__btn--active' : ''}`}
                onClick={() => setViewMode('grid')}
              >
                <img src={gridViewIcon} alt="Grid view" />
              </button>
              <button
                type="button"
                className={`cases-view-switch__btn${viewMode === 'list' ? ' cases-view-switch__btn--active' : ''}`}
                onClick={() => setViewMode('list')}
              >
                <img src={listViewIcon} alt="List view" />
              </button>
            </div>
            {canManageUsers && (
              <>
                <div className="cases-toolbar__divider" />
                <button type="button" className="cases-admin-btn" onClick={() => setUsersOpen(true)}>
                  Users
                </button>
              </>
            )}
            {canCreateCase && (
              <>
                <div className="cases-toolbar__divider" />
                <button type="button" className="cases-new-btn" onClick={() => setCreateOpen(true)}>
                  <img src={plusIcon} alt="" />
                  New Case
                </button>
              </>
            )}
          </div>
        </div>

        {successMessage && <p className="cases-create-success">{successMessage}</p>}

        <div className="cases-filters">
          <div className="cases-filters__left">
            {TABS.map((tab) => (
              <button
                type="button"
                key={tab.key}
                className={`cases-filter-pill${activeTab === tab.key ? ' cases-filter-pill--active' : ''}${
                  tab.key === 'flagged' ? ' cases-filter-pill--flagged' : ''
                }`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.key === 'flagged' && <span className="cases-filter-pill__dot" />}
                {tab.label} ({tabCounts[tab.key]})
              </button>
            ))}
          </div>
          <div className="cases-filters__right">
            <span className="cases-filters__sort-label">SORT BY:</span>
            <div className="cases-sort-wrap" ref={sortRef}>
              <button
                type="button"
                className="cases-sort"
                aria-haspopup="listbox"
                aria-expanded={sortOpen}
                onClick={() => setSortOpen((v) => !v)}
              >
                <span>{SORT_LABEL[sort]}</span>
                <img src={sortArrowIcon} alt="" />
              </button>
              {sortOpen && (
                <ul className="cases-sort-menu" role="listbox">
                  {SORT_OPTIONS.map((option) => (
                    <li key={option.key} role="none">
                      <button
                        type="button"
                        role="option"
                        aria-selected={sort === option.key}
                        className={`cases-sort-menu__item${sort === option.key ? ' cases-sort-menu__item--active' : ''}`}
                        onClick={() => {
                          setSort(option.key)
                          setSortOpen(false)
                        }}
                      >
                        {option.label}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        {loadState === 'loading' ? (
          <div className="cases-state">LOADING CASES…</div>
        ) : loadState === 'error' ? (
          <div className="cases-state cases-state--error">
            <p className="cases-state__title">UNABLE TO LOAD CASES</p>
            <p className="cases-state__detail">{errorMessage}</p>
            <button type="button" className="cases-state__retry" onClick={() => setRetryToken((t) => t + 1)}>
              RETRY
            </button>
          </div>
        ) : displayedCases.length === 0 ? (
          <div className="cases-state">NO CASES FOUND</div>
        ) : (
          <div className={`cases-grid${viewMode === 'list' ? ' cases-grid--list' : ''}`}>
            {displayedCases.map((apiCase, index) => {
              const caseItem = mapCaseToCard(apiCase, index)
              const remote = fetchedCases.some((item) => item.case_id === apiCase.case_id)
              const actions = visibleCaseCardActions(role, { archived: caseItem.archived, remote })
              return (
                <CaseCard
                  key={caseItem.id}
                  caseItem={caseItem}
                  starred={starredIds.has(caseItem.id)}
                  actions={actions}
                  onToggleStar={() => {
                    setStarredIds((prev) => {
                      const next = new Set(prev)
                      if (next.has(caseItem.id)) next.delete(caseItem.id)
                      else next.add(caseItem.id)
                      return next
                    })
                  }}
                  onOpen={() => onOpenCase?.(caseItem)}
                  onEdit={() => setEditCase(apiCase)}
                  onManageAccess={() => setAccessCase(apiCase)}
                  onComplete={async () => {
                    try {
                      const result = await completeCase(apiCase.case_id)
                      setFetchedCases((prev) =>
                        prev.map((item) => (item.case_id === apiCase.case_id ? { ...item, status: result.status } : item))
                      )
                      onCaseStatusChange?.(apiCase.case_id, result.status)
                      setSuccessMessage('Case marked completed.')
                    } catch (err) {
                      setSuccessMessage(err.message || 'Failed to mark case completed.')
                    }
                  }}
                  onRestore={async () => {
                    try {
                      const result = await restoreCase(apiCase.case_id)
                      setFetchedCases((prev) =>
                        prev.map((item) => (item.case_id === apiCase.case_id ? { ...item, status: result.status } : item))
                      )
                      onCaseStatusChange?.(apiCase.case_id, result.status)
                      setSuccessMessage('Case restored.')
                    } catch (err) {
                      setSuccessMessage(err.message || 'Failed to restore case.')
                    }
                  }}
                  onDelete={async () => {
                    if (!window.confirm('Delete this completed case permanently?')) return
                    try {
                      await deleteCase(apiCase.case_id)
                      setFetchedCases((prev) => prev.filter((item) => item.case_id !== apiCase.case_id))
                      onCaseRemoved?.(apiCase.case_id)
                      setSuccessMessage('Case deleted.')
                    } catch (err) {
                      setSuccessMessage(err.message || 'Failed to delete case.')
                    }
                  }}
                />
              )
            })}
          </div>
        )}

        <div className="cases-status-bar">
          <div className="cases-status-bar__left">
            <span className="cases-status-bar__item cases-status-bar__item--nominal">
              <span className="cases-status-bar__dot" />
              CLUSTER HEALTH: NOMINAL
            </span>
            <span className="cases-status-bar__sep">|</span>
            <span className="cases-status-bar__item">INGESTION RATE: 42.8 TX/S</span>
            <span className="cases-status-bar__sep">|</span>
            <span className="cases-status-bar__item">ACTIVE RECURSION DEPTH: 4</span>
          </div>
          <div className="cases-status-bar__right">
            <span className="cases-status-bar__item">SYNC HASH: 0x9bf4...e881</span>
            <span className="cases-status-bar__item cases-status-bar__item--link">EXPORT AUDIT DOCKET →</span>
          </div>
        </div>
      </main>

      {permissions.createCase && createOpen && (
        <CreateCaseModal
          onClose={() => setCreateOpen(false)}
          onCreate={async (draft) => {
            const created = await createCase(draft)
            setFetchedCases((prev) => [created, ...prev.filter((item) => item.case_id !== created.case_id)])
            onCreateCase?.(created)
            setCreateOpen(false)
            setSuccessMessage('Case created successfully.')
            if (activeTab === 'archived' || activeTab === 'flagged') setActiveTab('all')
          }}
        />
      )}

      {permissions.editCaseMetadata && editCase && (
        <EditCaseModal
          caseRecord={editCase}
          onClose={() => setEditCase(null)}
          onSave={async (draft) => {
            await onUpdateCase?.(draft)
            setEditCase(null)
            setSuccessMessage('Case changes saved.')
          }}
        />
      )}

      {permissions.manageCaseAccess && accessCase && (
        <CaseAccessModal caseRecord={accessCase} onClose={() => setAccessCase(null)} />
      )}

      {permissions.manageUsers && usersOpen && (
        <UserManagementModal onClose={() => setUsersOpen(false)} />
      )}
    </div>
  )
}

export default Cases
