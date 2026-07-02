import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const DETAIL_GRAPH_LIMIT = 180
const OVERVIEW_NODE_LIMIT = 220
const FOCUSED_NEIGHBOR_LIMIT = 180

const colorByType = {
  program: '#111827',
  host: '#0f172a',
  service: '#334155',
  route_family: '#2563eb',
  surface_component: '#7c3aed',
  surface_component_graph_signal: '#9333ea',
  surface_component_action_candidate: '#ea580c',
  endpoint: '#059669',
  route_template: '#0891b2',
  param: '#d97706',
  response_shape: '#64748b',
  artifact_ref: '#475569',
  neo4j_program: '#111827',
  neo4j_scope: '#475569',
  neo4j_ip: '#0369a1',
  neo4j_asn: '#0f766e',
  neo4j_cidr: '#0e7490',
  neo4j_js_file: '#ca8a04',
  neo4j_tool: '#78716c',
  neo4j_tool_run: '#92400e',
  neo4j_action_outcome: '#ea580c',
  neo4j_capability_profile: '#7c3aed',
  neo4j_outcome_feature: '#9333ea',
  neo4j_observation: '#0891b2',
  neo4j_evidence: '#0f766e',
  neo4j_surface_snapshot: '#1d4ed8',
  neo4j_surface_node: '#2563eb',
  neo4j_surface_fingerprint: '#64748b',
  neo4j_surface_delta: '#be123c',
  neo4j_projection_status: '#64748b',
  memory_fragment: '#7c3aed',
  action_run: '#ea580c',
  research_hypothesis: '#be123c',
  coverage_gap: '#dc2626',
}

const radiusByType = {
  program: 9,
  host: 8,
  service: 6,
  route_family: 5.5,
  surface_component: 7,
  surface_component_graph_signal: 4.2,
  surface_component_action_candidate: 4,
  endpoint: 3.6,
  route_template: 4,
  param: 3,
  response_shape: 3,
  artifact_ref: 2.8,
  neo4j_program: 9,
  neo4j_scope: 5,
  neo4j_ip: 5,
  neo4j_asn: 5,
  neo4j_cidr: 5,
  neo4j_js_file: 4,
  neo4j_tool: 4,
  neo4j_tool_run: 4,
  neo4j_action_outcome: 5,
  neo4j_capability_profile: 5,
  neo4j_outcome_feature: 3.8,
  neo4j_observation: 3.8,
  neo4j_evidence: 3.8,
  neo4j_surface_snapshot: 6,
  neo4j_surface_node: 3.8,
  neo4j_surface_fingerprint: 3.6,
  neo4j_surface_delta: 4.2,
  neo4j_projection_status: 6,
}

const overviewTypes = new Set(['program', 'host', 'service', 'route_family', 'surface_component', 'neo4j_program', 'neo4j_scope', 'neo4j_ip', 'neo4j_cidr', 'neo4j_asn', 'neo4j_surface_snapshot', 'neo4j_action_outcome'])
const alwaysLabelTypes = new Set(['program', 'host', 'surface_component', 'neo4j_program', 'neo4j_surface_snapshot', 'neo4j_projection_status'])

const useCanvasSize = () => {
  const containerRef = useRef(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const element = containerRef.current
    if (!element) return undefined
    const updateSize = () => {
      const rect = element.getBoundingClientRect()
      setSize({
        width: Math.max(320, Math.floor(rect.width)),
        height: Math.max(320, Math.floor(rect.height)),
      })
    }
    updateSize()
    const observer = new ResizeObserver(updateSize)
    observer.observe(element)
    window.addEventListener('resize', updateSize)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateSize)
    }
  }, [])

  return [containerRef, size]
}

const nodeKey = (node) => String(node?.id || '')

const endpointStatusColor = (node) => {
  const status = Number(node?.properties?.status_code || node?.metadata?.status_code)
  if (status >= 500) return '#dc2626'
  if (status >= 400) return '#f97316'
  if (status >= 300) return '#f59e0b'
  if (status >= 200) return '#16a34a'
  return colorByType.endpoint
}

const nodeColor = (node) => {
  if (node?.node_type === 'endpoint') return endpointStatusColor(node)
  if (String(node?.node_type || '').includes('gap')) return '#dc2626'
  return colorByType[node?.node_type] || '#64748b'
}

const nodeRadius = (node) => {
  const base = radiusByType[node?.node_type] || 4
  const count = Number(node?.metrics?.surface_node_count || node?.metrics?.endpoint_count || 0)
  if (count > 100) return base + 6
  if (count > 40) return base + 4
  if (count > 10) return base + 2
  return base
}

const nodeCaption = (node) => {
  const props = node?.properties || {}
  if (node?.node_type === 'endpoint') {
    const bits = [props.method, props.status_code, props.content_type].filter(Boolean)
    return bits.join(' · ')
  }
  if (node?.node_type === 'host' || node?.node_type === 'route_family') {
    return `${node?.metrics?.surface_node_count || 0} nodes`
  }
  return node?.caption || node?.node_type || ''
}

const truncate = (value, max = 42) => {
  const text = String(value || '')
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

const buildAdjacency = (links) => {
  const adjacency = new Map()
  const add = (source, target) => {
    if (!source || !target) return
    if (!adjacency.has(source)) adjacency.set(source, new Set())
    adjacency.get(source).add(target)
  }
  ;(links || []).forEach((link) => {
    add(link.source, link.target)
    add(link.target, link.source)
  })
  return adjacency
}

const normalizeGraph = (graph) => {
  const nodes = (graph?.nodes || []).map((node) => ({ ...node }))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const links = (graph?.edges || [])
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map((edge) => ({
      ...edge,
      source: edge.source,
      target: edge.target,
    }))
  return { nodes, links }
}

const scoreNode = (node) => {
  let score = 0
  if (overviewTypes.has(node?.node_type)) score += 1000
  score += Number(node?.metrics?.surface_node_count || 0) * 10
  score += Number(node?.evidence_refs?.length || 0)
  score += Number(node?.action_affordance_count || 0) * 4
  if (node?.staleness === 'fresh') score += 1
  return score
}

const selectCanvasGraph = (graph, selectedNode) => {
  const normalized = normalizeGraph(graph)
  const nodeById = new Map(normalized.nodes.map((node) => [node.id, node]))
  const adjacency = buildAdjacency(normalized.links)
  const visibleIds = new Set()
  const selectedId = selectedNode?.id

  if (selectedId && nodeById.has(selectedId)) {
    visibleIds.add(selectedId)
    ;[...(adjacency.get(selectedId) || [])]
      .map((id) => nodeById.get(id))
      .filter(Boolean)
      .sort((a, b) => scoreNode(b) - scoreNode(a))
      .slice(0, FOCUSED_NEIGHBOR_LIMIT)
      .forEach((node) => visibleIds.add(node.id))
  } else if (normalized.nodes.length > DETAIL_GRAPH_LIMIT) {
    normalized.nodes
      .filter((node) => overviewTypes.has(node.node_type) || node?.metadata?.ui_grouping)
      .sort((a, b) => scoreNode(b) - scoreNode(a))
      .slice(0, OVERVIEW_NODE_LIMIT)
      .forEach((node) => visibleIds.add(node.id))
  } else {
    normalized.nodes.forEach((node) => visibleIds.add(node.id))
  }

  const nodes = normalized.nodes.filter((node) => visibleIds.has(node.id))
  const links = normalized.links.filter((link) => visibleIds.has(link.source) && visibleIds.has(link.target))
  return {
    nodes,
    links,
    hiddenNodeCount: Math.max(0, normalized.nodes.length - nodes.length),
    mode: selectedId ? 'focused' : normalized.nodes.length > DETAIL_GRAPH_LIMIT ? 'overview' : 'investigation',
  }
}

const neighborSet = (links, nodeId) => {
  const set = new Set()
  if (!nodeId) return set
  links.forEach((link) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    if (source === nodeId) set.add(target)
    if (target === nodeId) set.add(source)
  })
  return set
}

const drawLabel = (ctx, text, x, y, scale, options = {}) => {
  const fontSize = Math.max(9 / scale, options.size || 11)
  ctx.font = `${options.weight || 600} ${fontSize}px Inter, ui-sans-serif, system-ui, sans-serif`
  const label = truncate(text, options.max || 46)
  const metrics = ctx.measureText(label)
  const paddingX = 4 / scale
  const paddingY = 2.5 / scale
  const width = metrics.width + paddingX * 2
  const height = fontSize + paddingY * 2
  const bx = x - width / 2
  const by = y + (options.offsetY || 9) / scale

  ctx.fillStyle = options.background || 'rgba(255,255,255,0.92)'
  ctx.strokeStyle = options.border || 'rgba(148,163,184,0.35)'
  ctx.lineWidth = 1 / scale
  ctx.beginPath()
  ctx.roundRect?.(bx, by, width, height, 4 / scale)
  if (!ctx.roundRect) ctx.rect(bx, by, width, height)
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = options.color || '#111827'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, x, by + height / 2)
}

const GraphLegend = memo(({ hiddenNodeCount, mode, totalNodes }) => (
  <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-xl rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs text-slate-700 shadow-sm backdrop-blur">
    <div className="font-semibold text-slate-900">Investigation graph</div>
    <div className="mt-1">
      Canvas renderer, hover/select to reveal labels, double click to focus. {hiddenNodeCount > 0 ? `${hiddenNodeCount} detail nodes hidden in ${mode} mode.` : `${totalNodes} nodes loaded.`}
    </div>
    <div className="mt-2 flex flex-wrap gap-2">
      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-slate-900" /> host</span>
      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-blue-600" /> route family</span>
      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-green-600" /> endpoint 2xx</span>
      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-purple-600" /> GDS signal</span>
      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-orange-500" /> 4xx/redirect</span>
      <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-sky-700" /> Neo4j projection</span>
    </div>
  </div>
))
GraphLegend.displayName = 'GraphLegend'

const GraphToolbar = ({ onZoomToFit, onFocusSelected, selectedNode }) => (
  <div className="absolute right-4 top-4 z-10 flex gap-2">
    <button
      type="button"
      onClick={onZoomToFit}
      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
    >
      Fit
    </button>
    <button
      type="button"
      disabled={!selectedNode}
      onClick={onFocusSelected}
      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45"
    >
      Focus selected
    </button>
  </div>
)

const emptyCanvasTitle = (boundary) => {
  const reason = boundary?.reason || ''
  if (['seed_required_for_template', 'snapshot_seed_required_for_surface_graph_math'].includes(reason)) {
    return 'Select a seed node'
  }
  if (reason === 'neo4j_template_empty_result') return 'Neo4j projection returned no rows'
  if (reason === 'neo4j_read_failed') return 'Neo4j read failed'
  if (reason === 'graph_projector_templates_unavailable') return 'Graph-projector templates unavailable'
  if (boundary?.status === 'unavailable') return 'Projection unavailable'
  return 'No graph projection loaded'
}

const EmptyCanvas = ({ graph }) => {
  const boundary = graph?.boundary || {}
  const title = emptyCanvasTitle(boundary)
  const message = boundary.message || 'Use Workbench data setup to build the read model.'
  const reason = boundary.reason || boundary.surface || ''
  const template = boundary.template_name || boundary.template
  return (
    <div className="flex h-full items-center justify-center rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 px-6">
      <div className="max-w-xl text-center">
        <div className="text-sm font-semibold text-gray-800">{title}</div>
        <div className="mt-1 text-sm text-gray-600">{message}</div>
        {(reason || template) && (
          <div className="mt-2 text-xs text-gray-500">
            {reason}{template ? ` · ${template}` : ''}
          </div>
        )}
      </div>
    </div>
  )
}

const CanvasBoundsStyle = () => (
  <style>{`
    .workbench-canvas-bounds { position: relative; overflow: hidden; isolation: isolate; }
    .workbench-canvas-bounds > div { max-width: 100% !important; max-height: 100% !important; overflow: hidden !important; }
    .workbench-canvas-bounds canvas { display: block !important; max-width: 100% !important; max-height: 100% !important; touch-action: none; }
  `}</style>
)

const GraphContextMenu = ({ menu, onClose, onInspect, onFocus, onCopyKey, onFilterType }) => {
  if (!menu?.node) return null
  const node = menu.node
  return (
    <div
      className="fixed z-50 w-64 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl"
      style={{ left: menu.x, top: menu.y }}
      role="menu"
    >
      <div className="border-b border-gray-100 px-3 py-2">
        <div className="truncate text-sm font-semibold text-gray-900" title={node.label}>{node.label}</div>
        <div className="mt-0.5 truncate text-xs text-gray-500" title={node.entity_key}>{node.node_type}</div>
      </div>
      <button type="button" onClick={() => { onInspect(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50">
        Inspect entity
      </button>
      <button type="button" onClick={() => { onFocus(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50">
        Focus graph from this seed
      </button>
      <button type="button" onClick={() => { onCopyKey(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50">
        Copy entity key
      </button>
      <button type="button" onClick={() => { onFilterType(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50">
        Filter left rail by this node type
      </button>
    </div>
  )
}

const WorkbenchCanvas = ({ graph, selectedNode, onSelectNode, onFocusNode, onCopyNodeKey, onFilterNodeType }) => {
  const graphRef = useRef(null)
  const [containerRef, canvasSize] = useCanvasSize()
  const [hoverNode, setHoverNode] = useState(null)
  const [contextMenu, setContextMenu] = useState(null)
  const selectedId = selectedNode?.id

  const canvasGraph = useMemo(() => selectCanvasGraph(graph, selectedNode), [graph, selectedNode])
  const nodeById = useMemo(() => new Map((graph?.nodes || []).map((node) => [node.id, node])), [graph])
  const visibleNodeById = useMemo(() => new Map(canvasGraph.nodes.map((node) => [node.id, node])), [canvasGraph.nodes])
  const highlightedNeighbors = useMemo(
    () => neighborSet(canvasGraph.links, hoverNode?.id || selectedId),
    [canvasGraph.links, hoverNode, selectedId],
  )

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setContextMenu(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])

  useEffect(() => {
    if (!graphRef.current || !canvasGraph.nodes.length) return
    const graphApi = graphRef.current
    graphApi.d3Force?.('charge')?.strength?.(canvasGraph.mode === 'focused' ? -150 : -260)
    graphApi.d3Force?.('link')?.distance?.((link) => {
      const sourceType = typeof link.source === 'object' ? link.source.node_type : ''
      const targetType = typeof link.target === 'object' ? link.target.node_type : ''
      if (sourceType === 'host' || targetType === 'host') return 95
      if (sourceType === 'route_family' || targetType === 'route_family') return 55
      return 38
    })
    graphApi.d3ReheatSimulation?.()
    const timer = window.setTimeout(() => graphApi.zoomToFit?.(450, 80), 450)
    return () => window.clearTimeout(timer)
  }, [canvasGraph.mode, canvasGraph.nodes.length, canvasGraph.links.length])

  useEffect(() => {
    if (!graphRef.current || !selectedId) return
    const node = visibleNodeById.get(selectedId)
    if (!node || !Number.isFinite(node.x) || !Number.isFinite(node.y)) return
    graphRef.current.centerAt?.(node.x, node.y, 450)
    graphRef.current.zoom?.(1.8, 450)
  }, [selectedId, visibleNodeById])

  const zoomToFit = useCallback(() => graphRef.current?.zoomToFit?.(450, 60), [])
  const focusSelected = useCallback(() => {
    if (selectedNode) onFocusNode?.(selectedNode)
  }, [onFocusNode, selectedNode])

  const inspectNode = useCallback((node) => {
    if (node) onSelectNode(nodeById.get(node.id) || node)
  }, [nodeById, onSelectNode])

  const focusNode = useCallback((node) => {
    if (node) onFocusNode?.(nodeById.get(node.id) || node)
  }, [nodeById, onFocusNode])

  const copyNodeKey = useCallback((node) => {
    const source = nodeById.get(node?.id) || node
    if (source?.entity_key) onCopyNodeKey?.(source.entity_key)
  }, [nodeById, onCopyNodeKey])

  const filterNodeType = useCallback((node) => {
    const source = nodeById.get(node?.id) || node
    if (source?.node_type) onFilterNodeType?.(source)
  }, [nodeById, onFilterNodeType])

  const paintNode = useCallback((node, ctx, globalScale) => {
    const selected = node.id === selectedId
    const hovered = node.id === hoverNode?.id
    const neighbor = highlightedNeighbors.has(node.id)
    const alwaysLabel = alwaysLabelTypes.has(node.node_type)
    const dimmed = (hoverNode || selectedId) && !selected && !hovered && !neighbor
    const radius = nodeRadius(node) * (selected ? 1.75 : hovered ? 1.45 : 1)

    ctx.globalAlpha = dimmed ? 0.25 : 1
    ctx.beginPath()
    ctx.arc(node.x || 0, node.y || 0, radius, 0, 2 * Math.PI, false)
    ctx.fillStyle = nodeColor(node)
    ctx.fill()
    ctx.lineWidth = (selected || hovered ? 2.2 : 0.9) / globalScale
    ctx.strokeStyle = selected ? '#2563eb' : hovered ? '#111827' : 'rgba(255,255,255,0.9)'
    ctx.stroke()

    const sparseEnoughForLabels = canvasGraph.nodes.length <= 80
    const zoomedEnoughForGroupLabels = globalScale > 1.9 && canvasGraph.nodes.length <= 160 && node.node_type !== 'endpoint'
    if (selected || hovered || alwaysLabel || (sparseEnoughForLabels && globalScale > 1.35 && !dimmed) || (zoomedEnoughForGroupLabels && !dimmed)) {
      drawLabel(ctx, node.label || node.id, node.x || 0, node.y || 0, globalScale, {
        size: selected || hovered ? 12 : 10,
        weight: selected || hovered ? 700 : 600,
        offsetY: radius + 4,
        color: selected ? '#1d4ed8' : '#111827',
        max: selected || hovered ? 56 : 24,
      })
    }

    if (hovered || selected) {
      const caption = nodeCaption(node)
      if (caption) {
        drawLabel(ctx, caption, node.x || 0, node.y || 0, globalScale, {
          size: 9,
          weight: 500,
          offsetY: radius + 22,
          color: '#475569',
          background: 'rgba(248,250,252,0.95)',
          max: 46,
        })
      }
    }
    ctx.globalAlpha = 1
  }, [highlightedNeighbors, hoverNode, selectedId])

  const linkColor = useCallback((link) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    if (!hoverNode && !selectedId) return 'rgba(100,116,139,0.22)'
    if (source === hoverNode?.id || target === hoverNode?.id || source === selectedId || target === selectedId) {
      return 'rgba(37,99,235,0.65)'
    }
    return 'rgba(148,163,184,0.10)'
  }, [hoverNode, selectedId])

  const linkWidth = useCallback((link) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    return source === selectedId || target === selectedId || source === hoverNode?.id || target === hoverNode?.id ? 1.8 : 0.6
  }, [hoverNode, selectedId])

  return (
    <div
      ref={containerRef}
      className="workbench-canvas-bounds relative isolate z-0 h-full w-full min-w-0 overflow-hidden bg-gray-50"
      data-testid="workbench-canvas-bounds"
    >
      <CanvasBoundsStyle />
      {!canvasGraph.nodes.length ? (
        <EmptyCanvas graph={graph} />
      ) : (
        <>
          <GraphLegend
        hiddenNodeCount={canvasGraph.hiddenNodeCount}
        mode={canvasGraph.mode}
        totalNodes={canvasGraph.nodes.length}
      />
          <GraphToolbar onZoomToFit={zoomToFit} onFocusSelected={focusSelected} selectedNode={selectedNode} />
          <ForceGraph2D
        ref={graphRef}
        width={canvasSize.width || 320}
        height={canvasSize.height || 320}
        graphData={canvasGraph}
        nodeId="id"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x || 0, node.y || 0, Math.max(8, nodeRadius(node) + 4), 0, 2 * Math.PI, false)
          ctx.fill()
        }}
        linkColor={linkColor}
        linkWidth={linkWidth}
        linkDirectionalParticles={(link) => (link.delta_state === 'added' || link.delta_state === 'changed' ? 1 : 0)}
        linkDirectionalParticleWidth={1.6}
        linkDirectionalParticleSpeed={0.006}
        enableNodeDrag
        cooldownTicks={80}
        d3VelocityDecay={0.34}
        onNodeHover={setHoverNode}
        onNodeClick={inspectNode}
        onNodeRightClick={(node, event) => {
          event.preventDefault()
          setContextMenu({ node, x: event.clientX, y: event.clientY })
        }}
        onNodeDoubleClick={focusNode}
        onBackgroundClick={() => setContextMenu(null)}
        onBackgroundRightClick={(event) => {
          event.preventDefault()
          setContextMenu(null)
        }}
      />
          <GraphContextMenu
            menu={contextMenu}
            onClose={() => setContextMenu(null)}
            onInspect={inspectNode}
            onFocus={focusNode}
            onCopyKey={copyNodeKey}
            onFilterType={filterNodeType}
          />
        </>
      )}
    </div>
  )
}

export default WorkbenchCanvas
