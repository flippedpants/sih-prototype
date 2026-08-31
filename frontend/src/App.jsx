import { useCallback, useEffect, useMemo, useState } from 'react'
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

  // Top 5 PERSON nodes by degree *within the selected cluster's own graph* —
  // computed from the already-fetched cluster_graph elements, never global degree.
  const keyPlayers = useMemo(() => {
    if (selectedClusterId === 'all' || !graph) return []
    const degreeById = new Map()
    const nameById = new Map()
    for (const element of graph.elements) {
      const data = element.data
      if (data.source !== undefined && data.target !== undefined) {
        degreeById.set(data.source, (degreeById.get(data.source) || 0) + 1)
        degreeById.set(data.target, (degreeById.get(data.target) || 0) + 1)
      } else {
        nameById.set(data.id, data.label)
      }
    }
    return [...degreeById.entries()]
      .map(([id, degree]) => ({ id, name: nameById.get(id) || id, degree }))
      .sort((a, b) => b.degree - a.degree)
      .slice(0, 5)
  }, [graph, selectedClusterId])

  const handleSelectCluster = useCallback((clusterId) => {
    setSelectedClusterId(clusterId)
    setSelectedEntityId(null)
  }, [])

  const handleSelectEntity = useCallback((entityId) => {
    setSelectedEntityId(entityId)
  }, [])

  // Search can find a person outside the currently viewed cluster, so jump
  // back to the full network so the result is guaranteed to be visible.
  const handleSelectSearchResult = useCallback((entityId) => {
    setSelectedClusterId('all')
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
          keyPlayers={keyPlayers}
          onSelectEntity={handleSelectEntity}
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
          onSelectSearchResult={handleSelectSearchResult}
        />
      </div>
      <StatsBar stats={stats} loading={statsLoading} error={statsError} />
    </div>
  )
}

export default App
