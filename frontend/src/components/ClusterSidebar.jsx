import ClusterDropdown from './ClusterDropdown.jsx'
import './ClusterSidebar.css'

const CASE_NAME = 'Cyber Fraud Investigation — Case 042'

function ClusterSidebar({ selectedClusterId, onSelectCluster, clusters, clustersLoading, clustersError }) {
  const isAllSelected = selectedClusterId === 'all'
  const selectedCluster = isAllSelected
    ? null
    : clusters.find((cluster) => cluster.id === selectedClusterId)

  return (
    <aside className="cluster-sidebar">
      <div className="panel-block sidebar-case-block">
        <span className="panel-label">Case</span>
        <h2 className="sidebar-case-name">{CASE_NAME}</h2>
      </div>

      <div className="panel-block">
        <span className="panel-label">Clusters</span>
        <ClusterDropdown
          clusters={clusters}
          selectedId={selectedClusterId}
          onSelect={onSelectCluster}
        />

        {clustersLoading && (
          <p className="cluster-stats-empty">Loading clusters…</p>
        )}
        {clustersError && (
          <p className="cluster-stats-empty">Failed to load clusters: {clustersError}</p>
        )}

        {selectedCluster && (
          <div className="cluster-stats-card">
            <span className="cluster-stats-name">{selectedCluster.name}</span>
            <div className="cluster-stats-row">
              <span className="cluster-stats-key">Entities</span>
              <span className="cluster-stats-value">{selectedCluster.entities}</span>
            </div>
            <div className="cluster-stats-row">
              <span className="cluster-stats-key">Links</span>
              <span className="cluster-stats-value">{selectedCluster.links}</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

export default ClusterSidebar
