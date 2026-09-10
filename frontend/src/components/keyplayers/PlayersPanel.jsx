import backArrowIcon from '../../assets/overview/back-arrow.svg'
import './PlayersPanel.css'

const TOP_DISPLAY_COUNT = 10

const SORT_TABS = [
  { key: 'betweenness', label: 'Betweenness' },
  { key: 'eigenvector', label: 'Eigen' },
  { key: 'degree', label: 'Degree' },
]

function formatRank(rank) {
  return `#${String(rank).padStart(2, '0')}`
}

function formatScore(score) {
  if (score === null || score === undefined || Number.isNaN(score)) return '—'
  return score.toFixed(3)
}

function buildRows(players) {
  const displayed = players.slice(0, TOP_DISPLAY_COUNT)
  const maxScore = Math.max(...displayed.map((p) => p.score ?? 0), 0.0001)

  return displayed.map((player) => ({
    rank: player.rank,
    nodeId: player.node_id,
    name: player.name || player.node_id,
    tag: (player.entity_type || 'PERSON').toUpperCase(),
    score: formatScore(player.score),
    barPct: Math.max(2, Math.round(((player.score ?? 0) / maxScore) * 100)),
  }))
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toISOString().slice(0, 10)
}

function ProfileField({ label, value }) {
  return (
    <div className="kp-profile__field">
      <span className="kp-profile__field-label">{label}</span>
      <span className="kp-profile__field-value">{value ?? '—'}</span>
    </div>
  )
}

function formatList(values) {
  return values && values.length > 0 ? values.join(', ') : '—'
}

function NodeProfile({ detailLoadState, nodeDetail, nodeNameById, onExitProfile, onRetry }) {
  return (
    <div className="kp-profile">
      <button type="button" className="kp-profile__back" onClick={onExitProfile}>
        <img src={backArrowIcon} alt="" />
        <span>Back to Key Players</span>
      </button>

      {detailLoadState === 'loading' && (
        <div className="kp-panel__state kp-panel__state--inline">LOADING PROFILE…</div>
      )}

      {detailLoadState === 'error' && (
        <div className="kp-panel__state kp-panel__state--inline kp-panel__state--error">
          <p className="kp-panel__state-title">UNABLE TO LOAD PERSON DETAIL</p>
          <button type="button" className="kp-panel__state-retry" onClick={onRetry}>
            RETRY
          </button>
        </div>
      )}

      {detailLoadState === 'not-found' && (
        <div className="kp-panel__state kp-panel__state--inline">PERSON NOT FOUND IN THIS CASE</div>
      )}

      {detailLoadState === 'ready' && nodeDetail && (
        <div className="kp-profile__body">
          <div className="kp-profile__score">
            <span className="kp-profile__score-value">{formatScore(nodeDetail.scores?.betweenness)}</span>
            <span className="kp-profile__score-label">BETWEENNESS SCORE</span>
          </div>

          <div className="kp-profile__section">
            <span className="kp-profile__section-title">IDENTITY</span>
            <div className="kp-profile__identity">
              <span className="kp-profile__name">{nodeDetail.name || nodeDetail.node_id}</span>
            </div>
            <div className="kp-profile__grid">
              <ProfileField label="PERSON ID" value={nodeDetail.node_id} />
              <ProfileField label="PHONE NUMBER" value={formatList(nodeDetail.phone_numbers)} />
              <ProfileField label="ACCOUNT NUMBER" value={formatList(nodeDetail.account_ids)} />
              <ProfileField label="ALIASES" value={formatList(nodeDetail.aliases)} />
            </div>
          </div>

          <div className="kp-profile__section">
            <span className="kp-profile__section-title">ENTITY DETAILS</span>
            <div className="kp-profile__grid">
              <ProfileField label="STRUCTURAL ROLE" value={nodeDetail.structural_role} />
              <ProfileField label="COMMUNITY ID" value={nodeDetail.community_id} />
              <ProfileField label="FIRST CONTACT" value={formatDate(nodeDetail.first_contact_date)} />
              <ProfileField label="CONNECTIONS" value={nodeDetail.connection_count} />
              {nodeDetail.structural_alert_count > 0 && (
                <ProfileField label="STRUCTURAL ALERTS" value={nodeDetail.structural_alert_count} />
              )}
            </div>
          </div>

          <div className="kp-profile__section kp-profile__section--ego">
            <span className="kp-profile__section-title kp-profile__section-title--accent">
              EGO NETWORK
              <span className="kp-profile__section-count">
                {nodeDetail.ego_network?.nodes?.length ?? 0} NODES · {nodeDetail.ego_network?.edges?.length ?? 0} EDGES
              </span>
            </span>
            <div className="kp-profile__ego-list">
              {(nodeDetail.ego_network?.edges ?? []).map((edge, i) => {
                const targetId = edge.source === nodeDetail.node_id ? edge.target : edge.source
                return (
                  <div key={`${edge.source}-${edge.target}-${i}`} className="kp-profile__ego-row">
                    <span className="kp-profile__ego-target">
                      {nodeNameById?.get(String(targetId)) || targetId}
                    </span>
                    <span className="kp-profile__ego-type">{edge.type}</span>
                  </div>
                )
              })}
              {(nodeDetail.ego_network?.edges ?? []).length === 0 && (
                <span className="kp-profile__ego-empty">NO DIRECT CONNECTIONS</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function PlayersPanel({
  loadState,
  errorMessage,
  players,
  sortMetric,
  onChangeSortMetric,
  selectedNodeId,
  onSelectPerson,
  onHoverPerson,
  onHoverEnd,
  nodeDetail,
  nodeNameById,
  detailLoadState,
  onRetry,
  profileMode,
  onExitProfile,
  onOpenProfile,
}) {
  const isLoading = loadState === 'loading'
  const isError = loadState === 'error'
  const isNotFound = loadState === 'not-found'
  const isNoCase = loadState === 'no-case'
  const isReady = loadState === 'ready'

  const rows = isReady ? buildRows(players ?? []) : []
  const showProfile = isReady && profileMode

  return (
    <aside className="kp-panel">
      <div className="kp-panel__header">
        <div className="kp-panel__header-top">
          <div className="kp-panel__title-row">
            <h2 className="kp-panel__title">{showProfile ? 'Detail View' : 'Key Players'}</h2>
            {!showProfile && <span className="kp-panel__top10-tag">TOP {TOP_DISPLAY_COUNT}</span>}
          </div>
        </div>
        {!showProfile && (
          <div className="kp-panel__sort-row">
            <span className="kp-panel__ranked-by">RANKED BY CENTRALITY ↓</span>
            <div className="kp-panel__sort-tabs">
              {SORT_TABS.map((tab, index) => (
                <span key={tab.key} className="kp-panel__sort-tab-group">
                  {index > 0 && <span className="kp-panel__sort-sep">|</span>}
                  <button
                    type="button"
                    className={`kp-panel__sort-tab${tab.key === sortMetric ? ' kp-panel__sort-tab--active' : ''}`}
                    onClick={() => onChangeSortMetric?.(tab.key)}
                    disabled={!isReady}
                  >
                    {tab.label}
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {isNoCase && <div className="kp-panel__state">RETURN TO CASES TO SELECT A CASE</div>}

      {isLoading && <div className="kp-panel__state">LOADING KEY PLAYERS…</div>}

      {isNotFound && <div className="kp-panel__state kp-panel__state--error">CASE NOT FOUND</div>}

      {isError && (
        <div className="kp-panel__state kp-panel__state--error">
          <p className="kp-panel__state-title">UNABLE TO LOAD KEY PLAYERS</p>
          <p className="kp-panel__state-detail">{errorMessage}</p>
          <button type="button" className="kp-panel__state-retry" onClick={onRetry}>
            RETRY
          </button>
        </div>
      )}

      {showProfile && (
        <NodeProfile
          detailLoadState={detailLoadState}
          nodeDetail={nodeDetail}
          nodeNameById={nodeNameById}
          onExitProfile={onExitProfile}
          onRetry={onRetry}
        />
      )}

      {isReady && !profileMode && rows.length === 0 && (
        <div className="kp-panel__state">NO RANKED PLAYERS AVAILABLE FOR THIS CASE</div>
      )}

      {isReady && !profileMode && rows.length > 0 && (
        <>
          <div className="kp-panel__scroll">
            {rows.map((row) => {
              const isSelected = row.nodeId === selectedNodeId
              return (
                <div
                  key={row.nodeId}
                  className={`kp-row${isSelected ? ' kp-row--top' : ''}`}
                  onClick={() => onSelectPerson?.(row.nodeId)}
                  onMouseEnter={() => onHoverPerson?.(row.nodeId)}
                  onMouseLeave={() => onHoverEnd?.()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(evt) => {
                    if (evt.key === 'Enter' || evt.key === ' ') onSelectPerson?.(row.nodeId)
                  }}
                >
                  <div className="kp-row__top">
                    <span className="kp-row__name">
                      <span className={`kp-row__rank${isSelected ? ' kp-row__rank--top' : ''}`}>
                        {formatRank(row.rank)}
                      </span>
                      <span className={`kp-row__name-text${isSelected ? ' kp-row__name-text--top' : ''}`}>
                        {row.name}
                      </span>
                    </span>
                    <span className="kp-row__right">
                      <span className="kp-row__tag kp-row__tag--default">{row.tag}</span>
                      <span className="kp-row__score">{row.score}</span>
                    </span>
                  </div>
                  <div className="kp-row__bar-track">
                    <span
                      className={`kp-row__bar-fill${isSelected ? ' kp-row__bar-fill--top' : ''}`}
                      style={{ width: `${row.barPct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          <div className="kp-panel__dossier">
            {detailLoadState === 'loading' && (
              <div className="kp-panel__state kp-panel__state--inline">LOADING DOSSIER…</div>
            )}
            {detailLoadState === 'error' && (
              <div className="kp-panel__state kp-panel__state--inline kp-panel__state--error">
                UNABLE TO LOAD PERSON DETAIL
              </div>
            )}
            {detailLoadState === 'not-found' && (
              <div className="kp-panel__state kp-panel__state--inline">PERSON NOT FOUND</div>
            )}
            {detailLoadState === 'ready' && nodeDetail && (
              <>
                <div className="kp-dossier__header">
                  <span className="kp-dossier__name">
                    <span className="kp-dossier__icon" aria-hidden="true">
                      ◆
                    </span>
                    {nodeDetail.name || nodeDetail.node_id}
                  </span>
                  <span className="kp-dossier__tag">
                    {(nodeDetail.structural_role || nodeDetail.entity_type || 'PERSON').toUpperCase()}
                  </span>
                </div>
                <div className="kp-dossier__stats">
                  <div className="kp-dossier__stat">
                    <span className="kp-dossier__stat-value">{nodeDetail.connection_count ?? '—'}</span>
                    <span className="kp-dossier__stat-label">DEGREE</span>
                  </div>
                  <div className="kp-dossier__stat">
                    <span className="kp-dossier__stat-value kp-dossier__stat-value--gold">
                      {formatScore(nodeDetail.scores?.betweenness)}
                    </span>
                    <span className="kp-dossier__stat-label">BETWEENNESS</span>
                  </div>
                  <div className="kp-dossier__stat">
                    <span className="kp-dossier__stat-value">{formatScore(nodeDetail.scores?.eigenvector)}</span>
                    <span className="kp-dossier__stat-label">EIGENVECTOR</span>
                  </div>
                </div>
                <button type="button" className="kp-dossier__btn" onClick={onOpenProfile}>
                  VIEW FULL ENTITY LEDGER →
                </button>
              </>
            )}
          </div>
        </>
      )}
    </aside>
  )
}

export default PlayersPanel
