import { useEffect, useRef } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import './NetworkGraph.css'

const STYLESHEET = [
  {
    selector: 'node',
    style: {
      shape: 'ellipse',
      'border-width': 0,
    },
  },
  {
    selector: 'node[kind="PERSON"]',
    style: {
      width: 6.5,
      height: 6.5,
      'background-color': 'data(color)',
    },
  },
  {
    selector: 'node.selected',
    style: {
      'underlay-opacity': 0.55,
      'underlay-padding': 5,
      'underlay-shape': 'ellipse',
    },
  },
  {
    selector: 'node[kind="PERSON"].selected',
    style: {
      width: 9.5,
      height: 9.5,
      'underlay-color': 'data(color)',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 0.4,
      'curve-style': 'haystack',
      'haystack-radius': 0,
      'line-color': '#202427',
      'target-arrow-shape': 'none',
      opacity: 0.7,
    },
  },
  {
    selector: 'edge[kind="FINANCIAL_LINK"]',
    style: {
      'line-style': 'dashed',
    },
  },
  {
    selector: 'edge.edge-highlighted',
    style: {
      'line-color': '#4a5257',
      width: 0.7,
      opacity: 1,
    },
  },
]

const LAYOUT = {
  name: 'cose',
  animate: false,
  fit: true,
  padding: 40,
  nodeRepulsion: 7000,
  idealEdgeLength: 60,
  gravity: 70,
  componentSpacing: 120,
}

function NetworkGraph({ clusterId, elements, selectedEntityId, onSelectEntity }) {
  const cyRef = useRef(null)

  // Attached directly on the concrete cy instance (fires once per instance,
  // including on remount when the cluster/key changes) rather than in a
  // separate effect, so listeners can never end up bound to a stale instance.
  // onSelectEntity is a stable callback (see App.jsx), so closing over it
  // here directly is safe.
  function handleCyInit(cy) {
    cyRef.current = cy
    cy.on('tap', 'node', (event) => {
      onSelectEntity(event.target.id())
    })
    cy.on('tap', (event) => {
      if (event.target === cy) {
        onSelectEntity(null)
      }
    })
  }

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.elements('.selected').removeClass('selected')
    cy.elements('.edge-highlighted').removeClass('edge-highlighted')

    if (!selectedEntityId) return

    const node = cy.getElementById(selectedEntityId)
    if (node.empty()) return

    const connectedEdges = node.connectedEdges()
    node.addClass('selected')
    connectedEdges.addClass('edge-highlighted')

    cy.animate(
      { center: { eles: node }, zoom: Math.max(cy.zoom(), 2.2) },
      { duration: 350 },
    )
  }, [selectedEntityId, elements])

  return (
    <CytoscapeComponent
      key={clusterId}
      elements={elements}
      stylesheet={STYLESHEET}
      layout={LAYOUT}
      className="network-graph-canvas"
      cy={handleCyInit}
    />
  )
}

export default NetworkGraph
