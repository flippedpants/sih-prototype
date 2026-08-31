import { useCallback, useEffect, useState } from 'react'
import Topbar from './components/Topbar.jsx'
import ClusterSidebar from './components/ClusterSidebar.jsx'
import NetworkGraph from './components/NetworkGraph.jsx'
import EntityPanel from './components/EntityPanel.jsx'
import StatsBar from './components/StatsBar.jsx'
import { fetchFullGraph, fetchClusterGraph, fetchListClusters } from './api/graph.js'
import { fetchEntityDetails } from './api/entities.js'
import { fetchStatistics } from './api/statistics.js'
import './App.css'

function App() {
  const [selectedClusterId, setSelectedClusterId] = useState('all')
  const [selectedEntityId, setSelectedEntityId] = useState(null)

  const [clusters, setClusters] = useState([])
  const [clustersLoading, setClustersLoading] = useState(true)
  const [clustersError, setClustersError] = useState(null)

  const [graph, setGraph] = useState(null)
  const [graphLoading, setGraphLoading] = useState(true)
  const [graphError, setGraphError] = useState(null)

  const [entity, setEntity] = useState(null)
  const [entityLoading, setEntityLoading] = useState(false)
  const [entityError, setEntityError] = useState(null)

  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [statsError, setStatsError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchStatistics()
      .then((result) => {
        if (cancelled) return
        setStats(result)
        setStatsLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        setStatsError(error.message)
        setStatsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchListClusters()
      .then((result) => {
        if (cancelled) return
        setClusters(result)
        setClustersLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        setClustersError(error.message)
        setClustersLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setGraphLoading(true)
    setGraphError(null)
    const request = selectedClusterId === 'all'
      ? fetchFullGraph()
      : fetchClusterGraph(selectedClusterId)
    request
      .then((result) => {
        if (cancelled) return
        setGraph(result)
        setGraphLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        setGraphError(error.message)
        setGraphLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedClusterId])

  useEffect(() => {
    if (!selectedEntityId) {
      setEntity(null)
      setEntityError(null)
      setEntityLoading(false)
      return undefined
    }
    let cancelled = false
    setEntityLoading(true)
    setEntityError(null)
    fetchEntityDetails(selectedEntityId)
      .then((result) => {
        if (cancelled) return
        setEntity(result)
        setEntityLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        setEntityError(error.message)
        setEntityLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedEntityId])

  const handleSelectCluster = useCallback((clusterId) => {
    setSelectedClusterId(clusterId)
    setSelectedEntityId(null)
  }, [])

  const handleSelectEntity = useCallback((entityId) => {
    setSelectedEntityId(entityId)
  }, [])

  return (
    <div className="app-shell">
      <Topbar />
      <div className="app-body">
        <ClusterSidebar
          selectedClusterId={selectedClusterId}
          onSelectCluster={handleSelectCluster}
          clusters={clusters}
          clustersLoading={clustersLoading}
          clustersError={clustersError}
        />
        <main className="graph-panel">
          <div className="graph-panel-header">
            <span className="panel-label">Network graph</span>
          </div>
          <div className="graph-panel-body">
            {graphError ? (
              <span className="graph-panel-message graph-panel-error">
                Failed to load network: {graphError}
              </span>
            ) : graphLoading || !graph ? (
              <span className="graph-panel-message">Loading network…</span>
            ) : (
              <NetworkGraph
                clusterId={graph.clusterId}
                elements={graph.elements}
                selectedEntityId={selectedEntityId}
                onSelectEntity={handleSelectEntity}
              />
            )}
          </div>
        </main>
        <EntityPanel
          entity={entity}
          entityLoading={entityLoading}
          entityError={entityError}
          onSelectEntity={handleSelectEntity}
        />
      </div>
      <StatsBar stats={stats} loading={statsLoading} error={statsError} />
    </div>
  )
}

export default App
