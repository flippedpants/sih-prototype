import { useEffect, useMemo, useRef, useState } from 'react'
import CaseHeader from '../components/overview/CaseHeader'
import Sidebar from '../components/overview/Sidebar'
import GraphViewport from '../components/overview/GraphViewport'
import OverviewNetworkGraph from '../components/overview/OverviewNetworkGraph'
import PlayersPanel from '../components/keyplayers/PlayersPanel'
import { fetchCaseOverview, fetchCaseGraph, fetchTopNodes, fetchNodeDetail } from '../api/overviewApi'
import { computeDegrees } from '../components/overview/graphLayout'
import './Overview.css'

const CUTOFF_VALUE = 0.75

function KeyPlayers({ caseId, onBack, onNavigate, cases, onSelectCase, navState }) {
  const [loadState, setLoadState] = useState(caseId ? 'loading' : 'no-case')
  const [overview, setOverview] = useState(null)
  const [graph, setGraph] = useState(null)
  const [players, setPlayers] = useState([])
  const [errorMessage, setErrorMessage] = useState(null)
  const [retryToken, setRetryToken] = useState(0)
  const [sortMetric, setSortMetric] = useState('betweenness')

  // Subset filters — same semantics as Overview: bridgingOnly/cutoffEnabled
  // re-fetch the graph against the API's real filter/cutoff params;
  // isolatesVisible is a pure client-side render filter.
  const [bridgingOnly, setBridgingOnly] = useState(false)
  const [cutoffEnabled, setCutoffEnabled] = useState(false)
  const [isolatesVisible, setIsolatesVisible] = useState(false)

  // Arriving via a graph-node click elsewhere (navState.selectedNodeId, e.g.
  // from Overview) opens straight into that person's full profile instead
  // of the default ranking list. This page gets a fresh mount every time
  // CASE_PAGES switches to it, so reading navState once at init (not in an
  // effect keyed on it) is enough - it can't go stale mid-visit.
  const [selectedNodeId, setSelectedNodeId] = useState(navState?.selectedNodeId ?? null)
  const [profileMode, setProfileMode] = useState(Boolean(navState?.selectedNodeId))
  const [nodeDetail, setNodeDetail] = useState(null)
  const [detailLoadState, setDetailLoadState] = useState('idle')

  const controlsRef = useRef(null)

  useEffect(() => {
    if (!caseId) {
      setLoadState('no-case')
      return
    }

    let cancelled = false

    async function load() {
      setLoadState('loading')
      setErrorMessage(null)
      try {
        const [overviewResult, graphResult, topNodesResult] = await Promise.all([
          fetchCaseOverview(caseId),
          fetchCaseGraph(caseId, {
            filter: bridgingOnly ? 'bridging_only' : undefined,
            cutoff: cutoffEnabled ? CUTOFF_VALUE : undefined,
          }),
          fetchTopNodes(caseId, { metric: sortMetric }),
        ])
        if (cancelled) return

        if (overviewResult === null) {
          setLoadState('not-found')
          return
        }

        setOverview(overviewResult)
        setGraph(graphResult)
        setPlayers(topNodesResult.results ?? [])
        setLoadState('ready')
      } catch (err) {
        if (cancelled) return
        setErrorMessage(err.message || 'Failed to load key players data')
        setLoadState('error')
      }
    }

    load()
    return () => {
      cancelled = true
    }
    // bridgingOnly/cutoffEnabled intentionally re-trigger a fetch: they're
    // real API query params, unlike isolatesVisible which is client-only.
  }, [caseId, retryToken, sortMetric, bridgingOnly, cutoffEnabled])

  // The ego network in the detail view only gets neighbor node_ids back from
  // the API (app/api/repository.py:get_node_detail never joins neighbor
  // names) — resolve them client-side against the full case graph this page
  // already has loaded, since ego-network neighbors are always case-scoped.
  const nodeNameById = useMemo(() => {
    const map = new Map()
    for (const node of graph?.nodes ?? []) {
      if (node.name) map.set(String(node.node_id), node.name)
    }
    return map
  }, [graph])

  const isolateCount = useMemo(() => {
    const nodes = graph?.nodes ?? []
    const edges = graph?.edges ?? []
    const degrees = computeDegrees(nodes, edges)
    return nodes.filter((n) => (degrees.get(String(n.node_id)) ?? 0) === 0).length
  }, [graph])

  // A fresh ranking (new case, or a different sort metric) resets which
  // person is selected — this is a new list, not an update to the old one.
  // Skipped while a node profile is open (arrived via navigation, or opened
  // by clicking the graph) so a background ranking reload can't kick the
  // user out of the profile they're looking at.
  useEffect(() => {
    if (profileMode) return
    setSelectedNodeId(players[0]?.node_id ?? null)
  }, [players])

  useEffect(() => {
    if (!caseId || !selectedNodeId) {
      setNodeDetail(null)
      setDetailLoadState('idle')
      return
    }

    let cancelled = false

    async function loadDetail() {
      setDetailLoadState('loading')
      try {
        const result = await fetchNodeDetail(caseId, selectedNodeId)
        if (cancelled) return
        setNodeDetail(result)
        setDetailLoadState(result ? 'ready' : 'not-found')
      } catch {
        if (cancelled) return
        setDetailLoadState('error')
      }
    }

    loadDetail()
    return () => {
      cancelled = true
    }
  }, [caseId, selectedNodeId])

  // Reflects a profile that was opened by a click (either arriving via
  // navState from another page, or the graph's own tap) in the graph's
  // highlight once it has actually rendered - not a default-on-load
  // highlight, since profileMode only ever turns on in response to a click.
  useEffect(() => {
    if (loadState === 'ready' && profileMode && selectedNodeId) {
      controlsRef.current?.selectNodeById(selectedNodeId)
    }
  }, [loadState, profileMode, selectedNodeId])

  const handleRetry = () => setRetryToken((t) => t + 1)

  // Graph highlighting only happens on an explicit click — the dossier
  // defaults to the #1 ranked player, but the graph itself stays unhighlighted
  // until the user actually clicks a row (or a node in the graph directly).
  const handleSelectPerson = (nodeId) => {
    setSelectedNodeId(nodeId)
    controlsRef.current?.selectNodeById(nodeId)
  }

  const handleHoverPerson = (nodeId) => controlsRef.current?.hoverNodeById(nodeId)
  const handleHoverEnd = () => controlsRef.current?.hoverNodeById(null)

  // Direct interaction with the graph itself opens/updates the full profile
  // view (the same behavior a graph-click navigation from another page
  // produces) - tapping empty space to clear exits back to the ranking list.
  const handleGraphNodeSelect = (nodeId) => {
    setSelectedNodeId(nodeId)
    setProfileMode(Boolean(nodeId))
  }

  const handleExitProfile = () => {
    setProfileMode(false)
    setSelectedNodeId(players[0]?.node_id ?? null)
    controlsRef.current?.clearSelection()
  }

  // "VIEW FULL ENTITY LEDGER" in the ranking list's inline dossier opens the
  // same full profile for whichever person that dossier is already showing.
  const handleOpenProfile = () => setProfileMode(true)

  const topPerson = players[0]

  // Sidebar badge counts, derived from data this page already loaded — no
  // extra requests just to populate the nav.
  const communityCount = overview?.community_count ?? undefined
  const keyPlayerCount = loadState === 'ready' ? players.length : undefined

  return (
    <div className="overview-page">
      <CaseHeader
        onBack={onBack}
        caseLabel={caseId || 'No case selected'}
        cases={cases}
        onSelectCase={onSelectCase}
        personNodes={graph?.nodes}
        onSelectPerson={handleGraphNodeSelect}
      />
      <div className="overview-page__body">
        <Sidebar
          active="key-players"
          onNavigate={onNavigate}
          isolatesVisible={isolatesVisible}
          isolateCount={isolateCount}
          onToggleIsolates={caseId ? () => setIsolatesVisible((v) => !v) : undefined}
          bridgingOnly={bridgingOnly}
          onToggleBridging={caseId ? () => setBridgingOnly((v) => !v) : undefined}
          cutoffEnabled={cutoffEnabled}
          onToggleCutoff={caseId ? () => setCutoffEnabled((v) => !v) : undefined}
          communityCount={communityCount}
          keyPlayerCount={keyPlayerCount}
          metrics={graph?.metrics}
        />
        <GraphViewport
          title="VIEWPORT: KEY PLAYER CENTRALITY MAP"
          docket={caseId || '—'}
          targetLabel="TOP NODE"
          {...(topPerson ? { targetValue: topPerson.name || topPerson.node_id } : {})}
          backgroundImage={null}
          onZoomIn={loadState === 'ready' ? () => controlsRef.current?.zoomIn() : undefined}
          onZoomOut={loadState === 'ready' ? () => controlsRef.current?.zoomOut() : undefined}
          onFit={loadState === 'ready' ? () => controlsRef.current?.fit() : undefined}
        >
          <OverviewNetworkGraph
            loadState={loadState}
            errorMessage={errorMessage}
            graph={graph}
            showIsolates={isolatesVisible}
            registerControls={(api) => {
              controlsRef.current = api
            }}
            onRetry={handleRetry}
            onNodeSelect={handleGraphNodeSelect}
          />
        </GraphViewport>
        <PlayersPanel
          loadState={loadState}
          errorMessage={errorMessage}
          players={players}
          sortMetric={sortMetric}
          onChangeSortMetric={setSortMetric}
          selectedNodeId={selectedNodeId}
          onSelectPerson={handleSelectPerson}
          onHoverPerson={handleHoverPerson}
          onHoverEnd={handleHoverEnd}
          nodeDetail={nodeDetail}
          nodeNameById={nodeNameById}
          detailLoadState={detailLoadState}
          onRetry={handleRetry}
          profileMode={profileMode}
          onExitProfile={handleExitProfile}
          onOpenProfile={handleOpenProfile}
        />
      </div>
    </div>
  )
}

export default KeyPlayers
