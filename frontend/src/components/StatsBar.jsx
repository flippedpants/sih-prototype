import './StatsBar.css'

function StatsBar({ stats, loading, error }) {
  return (
    <footer className="stats-bar">
      {error ? (
        <div className="stats-bar-item">
          <span className="stats-bar-label">Statistics</span>
          <span className="stats-bar-value stats-bar-value-error">Failed to load: {error}</span>
        </div>
      ) : loading || !stats ? (
        <div className="stats-bar-item">
          <span className="stats-bar-label">Statistics</span>
          <span className="stats-bar-value">Loading…</span>
        </div>
      ) : (
        stats.map((stat) => (
          <div className="stats-bar-item" key={stat.label}>
            <span className="stats-bar-label">{stat.label}</span>
            <span className="stats-bar-value">{stat.value}</span>
          </div>
        ))
      )}
    </footer>
  )
}

export default StatsBar
