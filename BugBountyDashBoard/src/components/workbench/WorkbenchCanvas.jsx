import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import {
  graphCounts,
  nodeTypeLabel,
  toNumber,
} from './workbenchGraphModel'

const DETAIL_GRAPH_LIMIT = 160
const OVERVIEW_NODE_LIMIT = 180
const FOCUSED_NEIGHBOR_LIMIT = 120

const colorByType = {
  program: '#f4f7fb',
  host: '#60a5fa',
  service: '#7dd3fc',
  route_family: '#f2cc60',
  surface_component: '#c084fc',
  surface_component_graph_signal: '#a78bfa',
  surface_component_action_candidate: '#ffb86c',
  endpoint: '#7ee787',
  route_template: '#38bdf8',
  param: '#ffb86c',
  response_shape: '#8b9bb0',
  artifact_ref: '#93c5fd',
  neo4j_program: '#f4f7fb',
  neo4j_scope: '#8b9bb0',
  neo4j_ip: '#60a5fa',
  neo4j_asn: '#7dd3fc',
  neo4j_cidr: '#38bdf8',
  neo4j_js_file: '#f2cc60',
  neo4j_tool: '#a3aab7',
  neo4j_tool_run: '#ffb86c',
  neo4j_action_outcome: '#f97316',
  neo4j_capability_profile: '#c084fc',
  neo4j_outcome_feature: '#a78bfa',
  neo4j_observation: '#38bdf8',
  neo4j_evidence: '#7dd3fc',
  neo4j_surface_snapshot: '#93c5fd',
  neo4j_surface_node: '#60a5fa',
  neo4j_surface_fingerprint: '#8b9bb0',
  neo4j_surface_delta: '#ff6b6b',
  neo4j_projection_status: '#8b9bb0',
  memory_fragment: '#c084fc',
  action_request: '#ffb86c',
  action_target: '#f2cc60',
  action_run: '#f97316',
  action_outcome: '#ffb86c',
  action_outcome_delta: '#38bdf8',
  research_hypothesis: '#ff6b6b',
  research_signal: '#a78bfa',
  coverage_overview: '#f4f7fb',
  coverage_lane: '#7dd3fc',
  coverage_gap: '#ff6b6b',
  checked_entity: '#7ee787',
  suggested_next_context: '#f2cc60',
}

const radiusByType = {
  program: 9,
  host: 8,
  service: 6,
  route_family: 5.5,
  surface_component: 7,
  surface_component_graph_signal: 4.2,
  surface_component_action_candidate: 4,
  endpoint: 3.8,
  route_template: 4,
  param: 3,
  response_shape: 3,
  artifact_ref: 2.8,
  coverage_overview: 9,
  coverage_lane: 7,
  coverage_gap: 5.5,
  checked_entity: 4.5,
  suggested_next_context: 4.5,
  action_request: 5,
  action_run: 5,
  action_outcome: 5,
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

const overviewTypes = new Set([
  'program',
  'host',
  'service',
  'route_family',
  'surface_component',
  'surface_component_graph_signal',
  'surface_component_action_candidate',
  'coverage_overview',
  'coverage_lane',
  'coverage_gap',
  'checked_entity',
  'neo4j_program',
  'neo4j_scope',
  'neo4j_ip',
  'neo4j_cidr',
  'neo4j_asn',
  'neo4j_surface_snapshot',
  'neo4j_action_outcome',
])
const alwaysLabelTypes = new Set(['program', 'host', 'surface_component', 'coverage_overview', 'coverage_gap', 'neo4j_program', 'neo4j_surface_snapshot', 'neo4j_projection_status'])

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
        height: Math.max(300, Math.floor(rect.height)),
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

const endpointStatusColor = (node) => {
  const status = Number(node?.properties?.status_code || node?.metadata?.status_code)
  if (status >= 500) return '#ff6b6b'
  if (status >= 400) return '#ffb86c'
  if (status >= 300) return '#f2cc60'
  if (status >= 200) return '#7ee787'
  return colorByType.endpoint
}

const nodeColor = (node) => {
  if (node?.node_type === 'endpoint') return endpointStatusColor(node)
  if (String(node?.node_type || '').includes('gap')) return '#ff6b6b'
  return colorByType[node?.node_type] || '#8b9bb0'
}

const nodeRadius = (node) => {
  const base = radiusByType[node?.node_type] || 4
  const count = Number(node?.metrics?.surface_node_count || node?.metrics?.node_count || node?.properties?.node_count || node?.metrics?.endpoint_count || 0)
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
  if (node?.node_type === 'surface_component') return node.caption || `${props.node_count || 0} nodes · ${props.changed_node_count || 0} changed`
  if (node?.node_type === 'host' || node?.node_type === 'route_family') return `${node?.metrics?.surface_node_count || 0} nodes`
  return node?.caption || nodeTypeLabel(node?.node_type)
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
    .map((edge) => ({ ...edge, source: edge.source, target: edge.target }))
  return { nodes, links }
}

const scoreNode = (node) => {
  let score = 0
  if (overviewTypes.has(node?.node_type)) score += 1000
  score += toNumber(node?.metrics?.surface_node_count || node?.metrics?.node_count || node?.properties?.node_count) * 10
  score += toNumber(node?.metrics?.changed_node_count || node?.properties?.changed_node_count) * 16
  score += toNumber(node?.evidence_refs?.length)
  score += toNumber(node?.action_affordance_count) * 12
  if (String(node?.node_type || '').includes('gap')) score += 200
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
  ctx.font = `${options.weight || 600} ${fontSize}px 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SFMono-Regular', Consolas, monospace`
  const label = truncate(text, options.max || 46)
  const metrics = ctx.measureText(label)
  const paddingX = 4 / scale
  const paddingY = 2.5 / scale
  const width = metrics.width + paddingX * 2
  const height = fontSize + paddingY * 2
  const bx = x - width / 2
  const by = y + (options.offsetY || 9) / scale

  ctx.fillStyle = options.background || 'rgba(11,15,20,0.94)'
  ctx.strokeStyle = options.border || 'rgba(125,211,252,0.28)'
  ctx.lineWidth = 1 / scale
  ctx.beginPath()
  ctx.roundRect?.(bx, by, width, height, 4 / scale)
  if (!ctx.roundRect) ctx.rect(bx, by, width, height)
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = options.color || '#d6deeb'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, x, by + height / 2)
}

const GraphLegend = memo(({ graph, hiddenNodeCount, mode, totalNodes }) => {
  const counts = graphCounts(graph)
  return (
    <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-xl rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs text-slate-700 shadow-sm backdrop-blur">
      <div className="font-semibold text-slate-900">Investigation graph</div>
      <div className="mt-1">
        Canvas renderer, hover/select to reveal labels, double click to focus.
        {' '}
        {hiddenNodeCount > 0 ? `${hiddenNodeCount} detail nodes hidden in ${mode} mode.` : `${totalNodes} nodes visible.`}
        {counts.neo4jRows ? ` ${counts.neo4jRows} Neo4j rows.` : ''}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-slate-900" /> host</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-blue-600" /> route/component</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-green-600" /> checked/2xx</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-purple-600" /> GDS signal</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-red-600" /> gap/delta</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-slate-400" /> relationship data</span>
      </div>
    </div>
  )
})
GraphLegend.displayName = 'GraphLegend'

const GraphToolbar = ({ onZoomToFit, onFocusSelected, selectedNode }) => (
  <div className="absolute right-4 top-4 z-10 flex gap-2">
    <button type="button" onClick={onZoomToFit} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50">
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

const EmptyCanvas = ({ graph }) => {
  const boundary = graph?.boundary || {}
  const title = boundary.status === 'seed_required' ? 'Select an entity first' : boundary.status === 'fallback' ? 'Relationship view is not ready' : 'Relationship view unavailable'
  const message = boundary.message || 'Run discovery, materialize Surface Components, or select a seed that exists in this lens.'
  const showTechnical = boundary.technical_projection_hidden_from_operator === false || boundary.show_technical === true
  const reason = showTechnical ? (boundary.reason || boundary.surface || '') : ''
  const template = showTechnical ? (boundary.template_name || boundary.template) : ''
  return (
    <div className="flex h-full items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 px-6">
      <div className="max-w-xl text-center">
        <div className="text-sm font-semibold text-slate-800">{title}</div>
        <div className="mt-1 text-sm text-slate-600">{message}</div>
        {(reason || template) && <div className="mt-2 text-xs text-slate-500">{reason}{template ? ` · ${template}` : ''}</div>}
      </div>
    </div>
  )
}

const CanvasBoundsStyle = () => (
  <style>{`
    .workbench-canvas-bounds { position: relative; overflow: hidden; isolation: isolate; background: #0b0f14; }
    .workbench-canvas-bounds::before {
      content: '';
      pointer-events: none;
      position: absolute;
      inset: 0;
      z-index: 1;
      background-image:
        linear-gradient(rgba(125, 211, 252, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(125, 211, 252, 0.025) 1px, transparent 1px);
      background-size: 32px 32px;
      opacity: 0.9;
    }
    .workbench-canvas-bounds > div { max-width: 100% !important; max-height: 100% !important; overflow: hidden !important; }
    .workbench-canvas-bounds canvas { display: block !important; max-width: 100% !important; max-height: 100% !important; touch-action: none; }
  `}</style>
)

const GraphContextMenu = ({ menu, onClose, onInspect, onFocus, onCopyKey, onFilterType }) => {
  if (!menu?.node) return null
  const node = menu.node
  return (
    <div className="fixed z-50 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl" style={{ left: menu.x, top: menu.y }} role="menu">
      <div className="border-b border-slate-100 px-3 py-2">
        <div className="truncate text-sm font-semibold text-slate-900" title={node.label}>{node.label}</div>
        <div className="mt-0.5 truncate text-xs text-slate-500" title={node.entity_key}>{nodeTypeLabel(node.node_type)}</div>
      </div>
      <button type="button" onClick={() => { onInspect(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Inspect entity</button>
      <button type="button" onClick={() => { onFocus(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Focus graph from this seed</button>
      <button type="button" onClick={() => { onCopyKey(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Copy entity key</button>
      <button type="button" onClick={() => { onFilterType(node); onClose() }} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Filter left rail by this node type</button>
    </div>
  )
}

const GraphCanvasOnly = ({ graph, selectedNode, canvasGraph, onSelectNode, onFocusNode, onCopyNodeKey, onFilterNodeType }) => {
  const graphRef = useRef(null)
  const [containerRef, canvasSize] = useCanvasSize()
  const [hoverNode, setHoverNode] = useState(null)
  const [contextMenu, setContextMenu] = useState(null)
  const selectedId = selectedNode?.id
  const nodeById = useMemo(() => new Map((graph?.nodes || []).map((node) => [node.id, node])), [graph])
  const visibleNodeById = useMemo(() => new Map(canvasGraph.nodes.map((node) => [node.id, node])), [canvasGraph.nodes])
  const highlightedNeighbors = useMemo(() => neighborSet(canvasGraph.links, hoverNode?.id || selectedId), [canvasGraph.links, hoverNode, selectedId])

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setContextMenu(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])

  useEffect(() => {
    if (!graphRef.current || !canvasGraph.nodes.length) return undefined
    const graphApi = graphRef.current
    graphApi.d3Force?.('charge')?.strength?.(canvasGraph.mode === 'focused' ? -160 : -280)
    graphApi.d3Force?.('link')?.distance?.((link) => {
      const sourceType = typeof link.source === 'object' ? link.source.node_type : ''
      const targetType = typeof link.target === 'object' ? link.target.node_type : ''
      if (sourceType === 'host' || targetType === 'host') return 95
      if (sourceType === 'surface_component' || targetType === 'surface_component') return 72
      if (sourceType === 'route_family' || targetType === 'route_family') return 56
      return 40
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
  const focusSelected = useCallback(() => { if (selectedNode) onFocusNode?.(selectedNode) }, [onFocusNode, selectedNode])
  const inspectNode = useCallback((node) => { if (node) onSelectNode(nodeById.get(node.id) || node) }, [nodeById, onSelectNode])
  const focusNode = useCallback((node) => { if (node) onFocusNode?.(nodeById.get(node.id) || node) }, [nodeById, onFocusNode])
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
    ctx.strokeStyle = selected ? '#7dd3fc' : hovered ? '#f4f7fb' : 'rgba(11,15,20,0.92)'
    ctx.stroke()

    const sparseEnoughForLabels = canvasGraph.nodes.length <= 80
    const zoomedEnoughForGroupLabels = globalScale > 1.9 && canvasGraph.nodes.length <= 160 && node.node_type !== 'endpoint'
    if (selected || hovered || alwaysLabel || (sparseEnoughForLabels && globalScale > 1.35 && !dimmed) || (zoomedEnoughForGroupLabels && !dimmed)) {
      drawLabel(ctx, node.label || node.id, node.x || 0, node.y || 0, globalScale, {
        size: selected || hovered ? 12 : 10,
        weight: selected || hovered ? 700 : 600,
        offsetY: radius + 4,
        color: selected ? '#7dd3fc' : '#d6deeb',
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
          color: '#8b9bb0',
          background: 'rgba(11,15,20,0.96)',
          max: 46,
        })
      }
    }
    ctx.globalAlpha = 1
  }, [canvasGraph.nodes.length, highlightedNeighbors, hoverNode, selectedId])

  const linkColor = useCallback((link) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    if (!hoverNode && !selectedId) return 'rgba(139,155,176,0.16)'
    if (source === hoverNode?.id || target === hoverNode?.id || source === selectedId || target === selectedId) return 'rgba(125,211,252,0.72)'
    return 'rgba(139,155,176,0.08)'
  }, [hoverNode, selectedId])

  const linkWidth = useCallback((link) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    return source === selectedId || target === selectedId || source === hoverNode?.id || target === hoverNode?.id ? 1.8 : 0.6
  }, [hoverNode, selectedId])

  return (
    <div ref={containerRef} className="workbench-canvas-bounds relative isolate z-0 h-full w-full min-w-0 overflow-hidden bg-gray-50" data-testid="workbench-canvas-bounds">
      <CanvasBoundsStyle />
      {!canvasGraph.nodes.length ? (
        <EmptyCanvas graph={graph} />
      ) : (
        <>
          <GraphLegend graph={graph} hiddenNodeCount={canvasGraph.hiddenNodeCount} mode={canvasGraph.mode} totalNodes={canvasGraph.nodes.length} />
          <GraphToolbar onZoomToFit={zoomToFit} onFocusSelected={focusSelected} selectedNode={selectedNode} />
          <ForceGraph2D
            ref={graphRef}
            width={canvasSize.width || 320}
            height={canvasSize.height || 320}
            backgroundColor="#0b0f14"
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
            onNodeRightClick={(node, event) => { event.preventDefault(); setContextMenu({ node, x: event.clientX, y: event.clientY }) }}
            onNodeDoubleClick={focusNode}
            onBackgroundClick={() => setContextMenu(null)}
            onBackgroundRightClick={(event) => { event.preventDefault(); setContextMenu(null) }}
          />
          <GraphContextMenu menu={contextMenu} onClose={() => setContextMenu(null)} onInspect={inspectNode} onFocus={focusNode} onCopyKey={copyNodeKey} onFilterType={filterNodeType} />
        </>
      )}
    </div>
  )
}

const WorkbenchCanvas = ({ graph, selectedNode, onSelectNode, onFocusNode, onCopyNodeKey, onFilterNodeType }) => {
  const canvasGraph = useMemo(() => selectCanvasGraph(graph, selectedNode), [graph, selectedNode])
  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <GraphCanvasOnly
        graph={graph}
        selectedNode={selectedNode}
        canvasGraph={canvasGraph}
        onSelectNode={onSelectNode}
        onFocusNode={onFocusNode}
        onCopyNodeKey={onCopyNodeKey}
        onFilterNodeType={onFilterNodeType}
      />
    </div>
  )
}

export default WorkbenchCanvas
