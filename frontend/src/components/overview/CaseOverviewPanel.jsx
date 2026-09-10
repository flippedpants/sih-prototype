import sortArrowIcon from '../../assets/overview/sort-arrow.svg'
import { scoreOf } from './graphLayout'
import './CaseOverviewPanel.css'

const PLAYER_BAR_COLORS = ['#d4af37', '#8d9aab', '#8d9aab', '#8d9aab', '#8d9aab']

function formatNumber(value) {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString()
}

function buildStats(overview) {
  return [
    {
      label: 'TOTAL ENTITIES',
      value: formatNumber(overview.total_entities),
    },
    {
      label: 'TOTAL RELATIONSHIPS',
      value: formatNumber(overview.total_relationships),
    },
    {
      label: 'COMMUNITIES',
      value: formatNumber(overview.community_count),
    },
    {
      label: 'STRUCTURAL ALERTS',
      value: formatNumber(overview.structural_alert_count),
      alert: (overview.structural_alert_count ?? 0) > 0,
    },
  ]
}

function buildPlayers(topPlayers) {
  const maxScore = Math.max(...topPlayers.map(scoreOf), 0.0001)

  return topPlayers.map((node, index) => {
    const score = scoreOf(node)
    return {
      rank: `#${String(index + 1).padStart(2, '0')}`,
      name: node.name || node.node_id,
      tag: (node.entity_type || 'ENTITY').toUpperCase(),
      score: score.toFixed(3),
      barPct: Math.round((score / maxScore) * 100),
      barColor: PLAYER_BAR_COLORS[index] || '#8d9aab',
      top: index === 0,
    }
  })
}

function CaseOverviewPanel({
  caseId,
  loadState,
  errorMessage,
  overview,
  topPlayers,
  summary,
  summaryLoadState,
  onRetry,
}) {
  const isLoading = loadState === 'loading'
  const isError = loadState === 'error'
  const isNotFound = loadState === 'not-found'
  const isNoCase = loadState === 'no-case'
  const isReady = loadState === 'ready' && overview

  const stats = isReady ? buildStats(overview) : []
  const players = isReady ? buildPlayers(topPlayers ?? []) : []

  return (
    <aside className="ov-panel">
      <div className="ov-panel__scroll">
        <div className="ov-panel__header">
          <div className="ov-panel__header-row">
            <h2 className="ov-panel__title">CASE OVERVIEW</h2>
            {isReady && (
              <span className="ov-panel__critical-tag">
                <span className="ov-panel__critical-dot" />
                {overview.structural_alert_count ?? 0} STRUCTURAL ALERT
                {overview.structural_alert_count === 1 ? '' : 'S'}
              </span>
            )}
          </div>
          <p className="ov-panel__docket">
            {isNoCase ? 'NO CASE SELECTED' : `DOCKET ${caseId}`}
          </p>
        </div>

        {isNoCase && (
          <div className="ov-panel__state">RETURN TO CASES TO SELECT A CASE</div>
        )}

        {isLoading && <div className="ov-panel__state">LOADING CASE OVERVIEW…</div>}

        {isNotFound && <div className="ov-panel__state ov-panel__state--error">CASE NOT FOUND</div>}

        {isError && (
          <div className="ov-panel__state ov-panel__state--error">
            <p className="ov-panel__state-title">UNABLE TO LOAD CASE OVERVIEW</p>
            <p className="ov-panel__state-detail">{errorMessage}</p>
            <button type="button" className="ov-panel__state-retry" onClick={onRetry}>
              RETRY
            </button>
          </div>
        )}

        {isReady && (
          <>
            <div className="ov-panel__stats">
              {stats.map((stat) => (
                <div key={stat.label} className={`ov-stat-card${stat.alert ? ' ov-stat-card--alert' : ''}`}>
                  <span className="ov-stat-card__label">{stat.label}</span>
                  <span className="ov-stat-card__value">{stat.value}</span>
                </div>
              ))}
            </div>

            <div className="ov-panel__summary">
              <div className="ov-panel__section-row">
                <span className="ov-panel__section-title">CASE SUMMARY</span>
              </div>
              {summaryLoadState === 'loading' && (
                <div className="ov-panel__state ov-panel__state--inline">GENERATING SUMMARY…</div>
              )}
              {summaryLoadState === 'error' && (
                <div className="ov-panel__state ov-panel__state--inline">UNABLE TO LOAD CASE SUMMARY</div>
              )}
              {summaryLoadState === 'not-found' && (
                <div className="ov-panel__state ov-panel__state--inline">NO SUMMARY GENERATED YET</div>
              )}
              {summaryLoadState === 'ready' && summary && (
                <p className="ov-panel__summary-text">{summary.summary_text}</p>
              )}
            </div>

            <div className="ov-panel__players">
              <div className="ov-panel__section-row">
                <span className="ov-panel__section-title">TOP KEY PLAYERS</span>
                <span className="ov-panel__sort">
                  RANKED BY BETW.
                  <img src={sortArrowIcon} alt="" />
                </span>
              </div>

              {players.length === 0 ? (
                <div className="ov-panel__state ov-panel__state--inline">NO RANKED ENTITIES AVAILABLE</div>
              ) : (
                <div className="ov-panel__players-list">
                  {players.map((player) => (
                    <div className="ov-player" key={player.rank}>
                      <div className="ov-player__row">
                        <span className="ov-player__name">
                          <span className={`ov-player__rank${player.top ? ' ov-player__rank--top' : ''}`}>
                            {player.rank}
                          </span>
                          <span className={`ov-player__name-text${player.top ? ' ov-player__name-text--top' : ''}`}>
                            {player.name}
                          </span>
                        </span>
                        <span className="ov-player__tag ov-player__tag--default">{player.tag}</span>
                      </div>
                      <div className="ov-player__row">
                        <span className="ov-player__bar-track">
                          <span
                            className="ov-player__bar-fill"
                            style={{ width: `${player.barPct}%`, background: player.barColor }}
                          />
                        </span>
                        <span className="ov-player__score" style={{ color: player.top ? player.barColor : undefined }}>
                          {player.score}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  )
}

export default CaseOverviewPanel
