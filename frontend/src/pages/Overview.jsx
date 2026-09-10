import { useEffect, useMemo, useRef, useState } from 'react'
import CaseHeader from '../components/overview/CaseHeader'
import Sidebar from '../components/overview/Sidebar'
import GraphViewport from '../components/overview/GraphViewport'
import CaseOverviewPanel from '../components/overview/CaseOverviewPanel'
import OverviewNetworkGraph from '../components/overview/OverviewNetworkGraph'
import { fetchCaseOverview, fetchCaseGraph, fetchCaseSummary } from '../api/overviewApi'
import { scoreOf, computeDegrees } from '../components/overview/graphLayout'
import './Overview.css'

const TOP_PLAYER_COUNT = 5
const CUTOFF_VALUE = 0.75

function Overview({ caseId, onBack, onNavigate, cases, onSelectCase }) {
  const [loadState, setLoadState] = useState(caseId ? 'loading' : 'no-case')
  const [overview, setOverview] = useState(null)
  const [graph, setGraph] = useState(null)
  const [summary, setSummary] = useState(null)
  const [summaryLoadState, setSummaryLoadState] = useState('loading')
  const [errorMessage, setErrorMessage] = useState(null)
  const [retryToken, setRetryToken] = useState(0)

  // Subset filters. bridgingOnly/cutoffEnabled trigger a real refetch against
  // the API's filter/cutoff params; isolatesVisible is a pure client-side
  // render filter (the API has no "isolates" concept). None of these apply
  // on initial load — the graph always starts unfiltered.
  const [bridgingOnly, setBridgingOnly] = useState(false)
  const [cutoffEnabled, setCutoffEnabled] = useState(false)
  const [isolatesVisible, setIsolatesVisible] = useState(false)

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
        const [overviewResult, graphResult] = await Promise.all([
          fetchCaseOverview(caseId),
          fetchCaseGraph(caseId, {
            filter: bridgingOnly ? 'bridging_only' : undefined,
            cutoff: cutoffEnabled ? CUTOFF_VALUE : undefined,
          }),
        ])
        if (cancelled) return

        if (overviewResult === null) {
          setLoadState('not-found')
          return
        }

        setOverview(overviewResult)
        setGraph(graphResult)
        setLoadState('ready')
      } catch (err) {
        if (cancelled) return
        setErrorMessage(err.message || 'Failed to load case data')
        setLoadState('error')
      }
    }

    load()
    return () => {
      cancelled = true
    }
    // bridgingOnly/cutoffEnabled intentionally re-trigger a fetch: they're
    // real API query params, unlike isolatesVisible which is client-only.
  }, [caseId, retryToken, bridgingOnly, cutoffEnabled])

  // Fetched independently from the overview/graph load above — a missing
  // summary (404) is the normal state for most cases right now, not an
  // error, so it must never block or fail the rest of the page.
  useEffect(() => {
    if (!caseId) {
      setSummary(null)
      setSummaryLoadState('no-case')
      return
    }

    let cancelled = false

    async function loadSummary() {
      setSummaryLoadState('loading')
      try {
        const result = await fetchCaseSummary(caseId)
        if (cancelled) return
        setSummary(result)
        setSummaryLoadState(result ? 'ready' : 'not-found')
      } catch {
        if (cancelled) return
        setSummary(null)
        setSummaryLoadState('error')
      }
    }

    loadSummary()
    return () => {
      cancelled = true
    }
  }, [caseId, retryToken])

  const topPlayers = useMemo(() => {
    const nodes = graph?.nodes ?? []
    return [...nodes].sort((a, b) => scoreOf(b) - scoreOf(a)).slice(0, TOP_PLAYER_COUNT)
  }, [graph])

  const isolateCount = useMemo(() => {
    const nodes = graph?.nodes ?? []
    const edges = graph?.edges ?? []
    const degrees = computeDegrees(nodes, edges)
    return nodes.filter((n) => (degrees.get(String(n.node_id)) ?? 0) === 0).length
  }, [graph])

  const targetValue = topPlayers[0]?.name || topPlayers[0]?.node_id

  // Sidebar badge counts, derived from data this page already loaded — no
  // extra requests just to populate the nav.
  const communityCount = overview?.community_count ?? undefined
  const keyPlayerCount = graph ? Math.min(10, graph.nodes.length) : undefined

  const handleRetry = () => setRetryToken((t) => t + 1)

  // Clicking a node here has nothing of its own to show it in (Overview has
  // no per-node panel) — hand off to Key Players, which does, carrying the
  // clicked node id so it opens straight into that person's profile.
  const handleNodeSelect = (nodeId) => {
    if (nodeId) onNavigate?.('key-players', { selectedNodeId: nodeId })
  }

  return (
    <div className="overview-page">
      <CaseHeader
        onBack={onBack}
        caseLabel={caseId || 'No case selected'}
        cases={cases}
        onSelectCase={onSelectCase}
        personNodes={graph?.nodes}
        onSelectPerson={handleNodeSelect}
      />
      <div className="overview-page__body">
        <Sidebar
          active="overview"
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
          docket={caseId || '—'}
          {...(targetValue ? { targetValue } : {})}
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
            onNodeSelect={handleNodeSelect}
          />
        </GraphViewport>
        <CaseOverviewPanel
          caseId={caseId}
          loadState={loadState}
          errorMessage={errorMessage}
          overview={overview}
          topPlayers={topPlayers}
          summary={summary}
          summaryLoadState={summaryLoadState}
          onRetry={handleRetry}
        />
      </div>
    </div>
  )
}

export default Overview
