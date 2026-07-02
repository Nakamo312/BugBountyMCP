import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import {
  buildLensStory,
  businessSignals,
  formatValue,
  graphCounts,
  importantNodes,
  lensPurpose,
  nodeTypeGroups,
  nodeTypeLabel,
  readableNodeMetrics,
  relationshipGroups,
  selectedNeighborhood,
  toNumber,
} from './workbenchGraphModel'

const DETAIL_GRAPH_LIMIT = 160
const OVERVIEW_NODE_LIMIT = 180
const FOCUSED_NEIGHBOR_LIMIT = 120

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
  action_request: '#92400e',
  action_target: '#d97706',
  action_run: '#ea580c',
  action_outcome: '#f97316',
  action_outcome_delta: '#0e7490',
  research_hypothesis: '#be123c',
  research_signal: '#9333ea',
  coverage_overview: '#111827',
  coverage_lane: '#2563eb',
  coverage_gap: '#dc2626',
  checked_entity: '#16a34a',
  suggested_next_context: '#ea580c',
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

const MetricPill = ({ label, value }) => (
  <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-0.5 text-sm font-semibold text-slate-900">{formatValue(value)}</div>
  </div>
)

const LensStory = memo(({ graph, selectedNode }) => {
  const story = buildLensStory(graph, selectedNode)
  return (
    <div className="border-b border-slate-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <div className="text-sm font-semibold text-slate-950">{story[0]?.value || 'Workbench read model'}</div>
          <div className="mt-1 text-xs text-slate-600">{lensPurpose(graph)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {story.slice(1).map((item) => (
            <MetricPill key={item.label} label={item.label} value={item.value} />
          ))}
        </div>
      </div>
    </div>
  )
})
LensStory.displayName = 'LensStory'

const SignalBoard = memo(({ graph, selectedNode, onSelectNode }) => {
  const sections = businessSignals(graph, selectedNode)
  if (!sections.length) return null
  return (
    <div className="grid gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 xl:grid-cols-3">
      {sections.slice(0, 6).map((section) => (
        <section key={section.id} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{section.label}</div>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{section.count}</span>
          </div>
          <div className="mt-2 space-y-1.5">
            {section.nodes.map((node) => (
              <button
                key={node.id}
                type="button"
                onClick={() => onSelectNode(node)}
                className="w-full rounded-lg border border-slate-100 px-2 py-1.5 text-left hover:bg-slate-50"
              >
                <div className="truncate text-xs font-semibold text-slate-900" title={node.label}>{node.label}</div>
                <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-slate-500">
                  <span className="truncate">{nodeTypeLabel(node.node_type)}</span>
                  <span>{readableNodeMetrics(node)[0]?.[1] ?? node.staleness ?? 'n/a'}</span>
                </div>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
})
SignalBoard.displayName = 'SignalBoard'

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
    .workbench-canvas-bounds { position: relative; overflow: hidden; isolation: isolate; }
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
  }, [canvasGraph.nodes.length, highlightedNeighbors, hoverNode, selectedId])

  const linkColor = useCallback((link) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    if (!hoverNode && !selectedId) return 'rgba(100,116,139,0.22)'
    if (source === hoverNode?.id || target === hoverNode?.id || source === selectedId || target === selectedId) return 'rgba(37,99,235,0.65)'
    return 'rgba(148,163,184,0.10)'
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

const RankingPanel = memo(({ graph, selectedNode, onSelectNode }) => {
  const scoped = selectedNode ? selectedNeighborhood(graph, selectedNode).nodes : graph?.nodes || []
  const ranked = importantNodes(scoped, 12)
  if (!ranked.length) return null
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-slate-200 bg-white p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Priority entities</div>
      <div className="mt-2 space-y-2">
        {ranked.map((node) => (
          <button key={node.id} type="button" onClick={() => onSelectNode(node)} className="w-full rounded-lg border border-slate-200 p-2 text-left hover:bg-slate-50">
            <div className="truncate text-xs font-semibold text-slate-900" title={node.label}>{node.label}</div>
            <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-slate-500">
              <span className="truncate">{nodeTypeLabel(node.node_type)}</span>
              <span>{Math.round(toNumber(node.confidence) * 100)}%</span>
            </div>
            {readableNodeMetrics(node).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {readableNodeMetrics(node).slice(0, 3).map(([label, value]) => (
                  <span key={label} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">{label}: {formatValue(value)}</span>
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
    </aside>
  )
})
RankingPanel.displayName = 'RankingPanel'

const RelationshipMatrix = memo(({ graph }) => {
  const nodeGroups = nodeTypeGroups(graph?.nodes || [])
  const edgeGroups = relationshipGroups(graph?.edges || [])
  if (!nodeGroups.length && !edgeGroups.length) return null
  return (
    <div className="grid gap-3 border-t border-slate-200 bg-white px-4 py-3 lg:grid-cols-2">
      <section className="rounded-xl border border-slate-200 p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Entity lanes</div>
        <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {nodeGroups.slice(0, 9).map((group) => (
            <div key={group.type} className="rounded-lg bg-slate-50 px-3 py-2">
              <div className="truncate text-xs font-semibold text-slate-900" title={group.label}>{group.label}</div>
              <div className="mt-1 text-[11px] text-slate-500">{group.count} nodes · {group.actionCount} actions · {group.evidenceCount} refs</div>
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-slate-200 p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Relationship lanes</div>
        <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {edgeGroups.slice(0, 9).map((group) => (
            <div key={group.type} className="rounded-lg bg-slate-50 px-3 py-2">
              <div className="truncate text-xs font-semibold text-slate-900" title={group.label}>{group.label}</div>
              <div className="mt-1 text-[11px] text-slate-500">{group.count} edges · {group.changed} changed</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
})
RelationshipMatrix.displayName = 'RelationshipMatrix'


const exposureLanes = [
  { id: 'asn', label: 'ASN', types: new Set(['neo4j_asn']) },
  { id: 'cidr', label: 'CIDR', types: new Set(['neo4j_cidr']) },
  { id: 'ip', label: 'IP', types: new Set(['neo4j_ip']) },
  { id: 'host', label: 'Host', types: new Set(['host', 'neo4j_host']) },
  { id: 'service', label: 'Service', types: new Set(['service', 'port']) },
  { id: 'endpoint', label: 'Endpoint', types: new Set(['endpoint', 'route_template']) },
  { id: 'parameter', label: 'Parameter', types: new Set(['param', 'parameter', 'neo4j_parameter']) },
  { id: 'request', label: 'Request / run', types: new Set(['action_request', 'action_target', 'action_run', 'neo4j_tool_run', 'neo4j_action_outcome']) },
  { id: 'evidence', label: 'Evidence', types: new Set(['artifact_ref', 'neo4j_observation', 'neo4j_evidence', 'neo4j_js_file']) },
]

const exposureLaneByType = new Map(exposureLanes.flatMap((lane) => [...lane.types].map((type) => [type, lane.id])))
const exposureLaneIndex = new Map(exposureLanes.map((lane, index) => [lane.id, index]))

const linkEndpointId = (value) => (typeof value === 'object' && value !== null ? value.id : value)
const exposureLaneId = (node) => exposureLaneByType.get(node?.node_type) || null
const exposureNodeTitle = (node) => node?.label || node?.properties?.identity_key || node?.id || 'entity'

const exposureNodeSubtitle = (node) => {
  const properties = node?.properties || {}
  const values = [
    properties.asn,
    properties.cidr,
    properties.address,
    properties.ip,
    properties.hostname,
    properties.host,
    properties.scheme && properties.port ? `${properties.scheme}:${properties.port}` : null,
    properties.method && (properties.route_template || properties.normalized_path || properties.path) ? `${properties.method} ${properties.route_template || properties.normalized_path || properties.path}` : null,
    properties.location,
    properties.status,
  ].filter(Boolean)
  return values[0] || node?.caption || nodeTypeLabel(node?.node_type)
}

const buildExposureTopology = (graph) => {
  const nodeById = new Map((graph?.nodes || []).map((node) => [node.id, node]))
  const laneItems = new Map(exposureLanes.map((lane) => [lane.id, []]))
  const nodeLinks = new Map()
  const laneEdges = new Map()

  ;(graph?.nodes || []).forEach((node) => {
    const laneId = exposureLaneId(node)
    if (!laneId) return
    laneItems.get(laneId).push(node)
    nodeLinks.set(node.id, [])
  })

  ;(graph?.edges || []).forEach((edge) => {
    const sourceId = linkEndpointId(edge.source)
    const targetId = linkEndpointId(edge.target)
    const source = nodeById.get(sourceId)
    const target = nodeById.get(targetId)
    const sourceLane = exposureLaneId(source)
    const targetLane = exposureLaneId(target)
    if (!sourceLane || !targetLane || sourceLane === targetLane) return
    const leftLane = exposureLaneIndex.get(sourceLane) <= exposureLaneIndex.get(targetLane) ? sourceLane : targetLane
    const rightLane = leftLane === sourceLane ? targetLane : sourceLane
    const laneKey = `${leftLane}->${rightLane}:${edge.relationship_type || edge.label || 'RELATED'}`
    laneEdges.set(laneKey, {
      sourceLane: leftLane,
      targetLane: rightLane,
      type: edge.relationship_type || edge.label || 'RELATED',
      count: (laneEdges.get(laneKey)?.count || 0) + 1,
    })
    nodeLinks.get(sourceId)?.push({ edge, node: target })
    nodeLinks.get(targetId)?.push({ edge, node: source })
  })

  const lanes = exposureLanes.map((lane) => ({
    ...lane,
    nodes: importantNodes(laneItems.get(lane.id) || [], 24),
    total: (laneItems.get(lane.id) || []).length,
  }))
  return {
    lanes,
    laneEdges: [...laneEdges.values()].sort((a, b) => b.count - a.count || a.type.localeCompare(b.type)),
    nodeLinks,
    totals: {
      nodes: lanes.reduce((sum, lane) => sum + lane.total, 0),
      edges: (graph?.edges || []).length,
    },
  }
}

const ExposureMetric = ({ label, value }) => (
  <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-0.5 text-sm font-semibold text-slate-900">{formatValue(value)}</div>
  </div>
)

const ExposureNodeCard = ({ node, links, selectedNode, onSelectNode, onFocusNode }) => {
  const selected = selectedNode?.id === node.id
  const shownLinks = (links || []).slice(0, 3)
  return (
    <button
      type="button"
      onClick={() => onSelectNode?.(node)}
      onDoubleClick={() => onFocusNode?.(node)}
      className={`w-full rounded-xl border p-2 text-left transition ${selected ? 'border-blue-500 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'}`}
    >
      <div className="flex items-start gap-2">
        <i className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: nodeColor(node) }} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-slate-900" title={exposureNodeTitle(node)}>{exposureNodeTitle(node)}</div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500" title={exposureNodeSubtitle(node)}>{exposureNodeSubtitle(node)}</div>
        </div>
      </div>
      {shownLinks.length > 0 && (
        <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
          {shownLinks.map(({ edge, node: other }) => (
            <div key={`${edge.id}:${other?.id}`} className="truncate text-[10px] text-slate-500" title={`${edge.relationship_type || edge.label} → ${other?.label}`}>
              {edge.relationship_type || edge.label} → {other?.label || other?.id}
            </div>
          ))}
        </div>
      )}
    </button>
  )
}

const ExposureTopologyCanvas = ({ graph, selectedNode, onSelectNode, onFocusNode }) => {
  const topology = useMemo(() => buildExposureTopology(graph), [graph])
  if (!topology.totals.nodes) {
    return <GraphCanvasOnly graph={graph} selectedNode={selectedNode} canvasGraph={selectCanvasGraph(graph, selectedNode)} onSelectNode={onSelectNode} onFocusNode={onFocusNode} />
  }
  return (
    <div className="workbench-canvas-bounds h-full min-h-0 overflow-auto bg-gray-50 p-4" data-testid="exposure-topology-canvas">
      <CanvasBoundsStyle />
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-blue-700">Neo4j exposure topology</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">ASN → CIDR → IP → Host → Service → Endpoint → Parameter → Request</h2>
            <p className="mt-1 max-w-5xl text-sm text-slate-600">Projected ontology view from graph-projector: autonomous systems, ranges, resolved infrastructure, exposed services, endpoints, parameters, action/run/evidence context.</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">Template {graph?.boundary?.template_name || 'asset_exposure'}</div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-6 xl:grid-cols-9">
          {topology.lanes.map((lane) => <ExposureMetric key={lane.id} label={lane.label} value={lane.total} />)}
        </div>
      </div>
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Relationship lanes</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {topology.laneEdges.slice(0, 18).map((edge) => (
            <span key={`${edge.sourceLane}:${edge.targetLane}:${edge.type}`} className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700">
              {edge.sourceLane} → {edge.targetLane}: {edge.type} · {edge.count}
            </span>
          ))}
          {!topology.laneEdges.length && <span className="text-xs text-slate-500">No cross-layer relationships returned yet.</span>}
        </div>
      </div>
      <div className="grid min-w-[1180px] grid-cols-9 gap-3">
        {topology.lanes.map((lane) => (
          <section key={lane.id} className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{lane.label}</div>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700">{lane.total}</span>
            </div>
            <div className="mt-3 space-y-2">
              {lane.nodes.map((node) => <ExposureNodeCard key={node.id} node={node} links={topology.nodeLinks.get(node.id)} selectedNode={selectedNode} onSelectNode={onSelectNode} onFocusNode={onFocusNode} />)}
              {!lane.nodes.length && <div className="rounded-lg border border-dashed border-slate-200 px-2 py-6 text-center text-[11px] text-slate-400">empty</div>}
              {lane.total > lane.nodes.length && <div className="rounded-lg bg-slate-50 px-2 py-1.5 text-[11px] text-slate-500">{lane.total - lane.nodes.length} hidden</div>}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}


const surfaceNodeTypes = new Set(['host', 'service', 'port', 'endpoint', 'route_template', 'param', 'response_shape'])

const textValue = (value, fallback = 'unknown') => {
  const text = String(value ?? '').trim()
  return text || fallback
}

const surfaceHost = (node) => textValue(node?.properties?.host || node?.metadata?.features?.host, 'unknown-host')

const surfacePath = (node) => textValue(
  node?.properties?.route_template || node?.metadata?.features?.route_template || node?.properties?.path || node?.metadata?.features?.path,
  '/',
)

const surfaceFamily = (node) => {
  const path = surfacePath(node)
  const clean = path.startsWith('/') ? path : `/${path}`
  const parts = clean.split('/').filter(Boolean)
  if (!parts.length) return '/'
  return parts.length > 1 ? `/${parts[0]}/*` : `/${parts[0]}`
}

const statusBucket = (node) => {
  const status = Number(node?.properties?.status_code || node?.metadata?.features?.status_code)
  if (!Number.isFinite(status)) return null
  if (status >= 500) return '5xx'
  if (status >= 400) return '4xx'
  if (status >= 300) return '3xx'
  if (status >= 200) return '2xx'
  return String(status)
}

const increment = (map, key) => {
  if (!key) return
  map.set(key, (map.get(key) || 0) + 1)
}

const countText = (map, empty = 'none') => {
  const rows = [...map.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 4)
  return rows.length ? rows.map(([key, value]) => `${key} ${value}`).join(' · ') : empty
}

const surfaceNodeRank = (node) => {
  const order = { endpoint: 0, route_template: 1, param: 2, response_shape: 3, service: 4, port: 5, host: 6 }
  return order[node?.node_type] ?? 9
}

const buildSurfaceMap = (graph) => {
  const rawNodes = (graph?.nodes || []).filter((node) => surfaceNodeTypes.has(node.node_type) && !node?.metadata?.ui_grouping)
  const hostMap = new Map()
  const groupMap = new Map()

  rawNodes.forEach((node) => {
    const host = surfaceHost(node)
    const family = surfaceFamily(node)
    const hostEntry = hostMap.get(host) || {
      host,
      nodes: [],
      groups: new Map(),
      methods: new Map(),
      statuses: new Map(),
      changed: 0,
      actions: 0,
      evidence: 0,
    }
    const groupKey = `${host}\n${family}`
    const group = groupMap.get(groupKey) || {
      id: groupKey,
      host,
      family,
      nodes: [],
      endpoints: [],
      params: [],
      responses: [],
      services: [],
      methods: new Map(),
      statuses: new Map(),
      changed: 0,
      actions: 0,
      evidence: 0,
      representative: null,
    }

    hostEntry.nodes.push(node)
    group.nodes.push(node)
    hostEntry.actions += toNumber(node.action_affordance_count)
    group.actions += toNumber(node.action_affordance_count)
    hostEntry.evidence += (node.evidence_refs || []).length
    group.evidence += (node.evidence_refs || []).length
    if (['fresh', 'stale'].includes(node.staleness)) {
      hostEntry.changed += 1
      group.changed += 1
    }

    const method = textValue(node?.properties?.method || node?.metadata?.features?.method, '')
    const bucket = statusBucket(node)
    increment(hostEntry.methods, method)
    increment(group.methods, method)
    increment(hostEntry.statuses, bucket)
    increment(group.statuses, bucket)

    if (node.node_type === 'endpoint' || node.node_type === 'route_template') group.endpoints.push(node)
    if (node.node_type === 'param') group.params.push(node)
    if (node.node_type === 'response_shape') group.responses.push(node)
    if (node.node_type === 'service' || node.node_type === 'port') group.services.push(node)
    if (!group.representative || surfaceNodeRank(node) < surfaceNodeRank(group.representative)) group.representative = node

    hostEntry.groups.set(groupKey, group)
    hostMap.set(host, hostEntry)
    groupMap.set(groupKey, group)
  })

  const scoreGroup = (group) => group.endpoints.length * 8 + group.params.length * 3 + group.responses.length * 2 + group.changed * 10 + group.actions * 12 + group.evidence
  const hosts = [...hostMap.values()]
    .map((host) => ({
      ...host,
      groups: [...host.groups.values()].sort((a, b) => scoreGroup(b) - scoreGroup(a) || a.family.localeCompare(b.family)),
      endpointCount: [...host.groups.values()].reduce((sum, group) => sum + group.endpoints.length, 0),
      paramCount: [...host.groups.values()].reduce((sum, group) => sum + group.params.length, 0),
      responseCount: [...host.groups.values()].reduce((sum, group) => sum + group.responses.length, 0),
    }))
    .sort((a, b) => b.endpointCount - a.endpointCount || b.nodes.length - a.nodes.length || a.host.localeCompare(b.host))

  return {
    hosts,
    totals: {
      hosts: hosts.length,
      families: groupMap.size,
      endpoints: hosts.reduce((sum, host) => sum + host.endpointCount, 0),
      params: hosts.reduce((sum, host) => sum + host.paramCount, 0),
      responses: hosts.reduce((sum, host) => sum + host.responseCount, 0),
      changed: hosts.reduce((sum, host) => sum + host.changed, 0),
    },
  }
}

const isSurfaceSelection = (selectedNode, host, family) => {
  if (!selectedNode) return false
  return surfaceHost(selectedNode) === host && surfaceFamily(selectedNode) === family
}

const SurfaceMapMetric = ({ label, value }) => (
  <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-0.5 text-sm font-semibold text-slate-900">{formatValue(value)}</div>
  </div>
)

const SurfaceRouteBand = ({ group, selectedNode, onSelectNode, onFocusNode }) => {
  const selected = isSurfaceSelection(selectedNode, group.host, group.family)
  const examples = [...group.endpoints]
    .sort((a, b) => String(a.label).localeCompare(String(b.label)))
    .slice(0, 4)
  const representative = group.representative || group.nodes[0]
  const select = () => representative && onSelectNode?.(representative)
  const focus = () => representative && onFocusNode?.(representative)

  return (
    <button
      type="button"
      onClick={select}
      onDoubleClick={focus}
      className={`w-full rounded-xl border p-3 text-left transition ${selected ? 'border-blue-500 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-900" title={`${group.host}${group.family}`}>{group.family}</div>
          <div className="mt-1 text-[11px] text-slate-500">{group.nodes.length} surface nodes · {group.evidence} evidence refs</div>
        </div>
        <div className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700">{group.endpoints.length} endpoints</div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        <div className="rounded-lg bg-slate-50 px-2 py-1.5"><span className="text-[10px] uppercase text-slate-500">Methods</span><div className="truncate text-xs font-medium text-slate-800">{countText(group.methods)}</div></div>
        <div className="rounded-lg bg-slate-50 px-2 py-1.5"><span className="text-[10px] uppercase text-slate-500">Responses</span><div className="truncate text-xs font-medium text-slate-800">{countText(group.statuses)}</div></div>
        <div className="rounded-lg bg-slate-50 px-2 py-1.5"><span className="text-[10px] uppercase text-slate-500">Inputs</span><div className="truncate text-xs font-medium text-slate-800">{group.params.length} params</div></div>
        <div className="rounded-lg bg-slate-50 px-2 py-1.5"><span className="text-[10px] uppercase text-slate-500">Delta</span><div className="truncate text-xs font-medium text-slate-800">{group.changed || 0} changed</div></div>
      </div>
      {examples.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {examples.map((node) => <span key={node.id} className="max-w-[14rem] truncate rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-700">{node.label}</span>)}
        </div>
      )}
      <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
        <span>{group.responses.length} response shapes · {group.actions} action links</span>
        <span className="font-semibold text-blue-700">Double click to focus</span>
      </div>
    </button>
  )
}

const SurfaceHostSection = ({ host, selectedNode, onSelectNode, onFocusNode }) => (
  <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
      <div className="min-w-0">
        <div className="truncate text-base font-semibold text-slate-950" title={host.host}>{host.host}</div>
        <div className="mt-1 text-xs text-slate-500">{host.groups.length} route families · {host.endpointCount} endpoints · {host.paramCount} params · {host.responseCount} response shapes</div>
      </div>
      <div className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">{host.nodes.length} nodes</div>
    </div>
    <div className="mt-3 space-y-2">
      {host.groups.slice(0, 18).map((group) => (
        <SurfaceRouteBand key={group.id} group={group} selectedNode={selectedNode} onSelectNode={onSelectNode} onFocusNode={onFocusNode} />
      ))}
      {host.groups.length > 18 && <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">{host.groups.length - 18} route families hidden. Focus or search to narrow the map.</div>}
    </div>
  </section>
)

const SurfaceMapCanvas = ({ graph, selectedNode, onSelectNode, onFocusNode }) => {
  const surfaceMap = useMemo(() => buildSurfaceMap(graph), [graph])
  if (!surfaceMap.hosts.length) {
    return <GraphCanvasOnly graph={graph} selectedNode={selectedNode} canvasGraph={selectCanvasGraph(graph, selectedNode)} onSelectNode={onSelectNode} onFocusNode={onFocusNode} />
  }
  const visibleHosts = surfaceMap.hosts.slice(0, 12)
  return (
    <div className="workbench-canvas-bounds h-full min-h-0 overflow-y-auto bg-gray-50 p-4" data-testid="surface-map-canvas">
      <CanvasBoundsStyle />
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-blue-700">Surface Map</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">Host → route family → endpoint topology</h2>
            <p className="mt-1 max-w-4xl text-sm text-slate-600">Canonical snapshot grouped from surface_nodes: hosts, route families, endpoints, params, responses, deltas, evidence, actions.</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">Snapshot {truncate(graph?.snapshot_id || 'latest', 20)}</div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <SurfaceMapMetric label="Hosts" value={surfaceMap.totals.hosts} />
          <SurfaceMapMetric label="Route families" value={surfaceMap.totals.families} />
          <SurfaceMapMetric label="Endpoints" value={surfaceMap.totals.endpoints} />
          <SurfaceMapMetric label="Params" value={surfaceMap.totals.params} />
          <SurfaceMapMetric label="Responses" value={surfaceMap.totals.responses} />
          <SurfaceMapMetric label="Changed" value={surfaceMap.totals.changed} />
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        {visibleHosts.map((host) => (
          <SurfaceHostSection key={host.host} host={host} selectedNode={selectedNode} onSelectNode={onSelectNode} onFocusNode={onFocusNode} />
        ))}
      </div>
      {surfaceMap.hosts.length > visibleHosts.length && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">{surfaceMap.hosts.length - visibleHosts.length} hosts hidden. Use search or focus a seed to inspect the rest.</div>
      )}
    </div>
  )
}

const WorkbenchCanvas = ({ graph, selectedNode, onSelectNode, onFocusNode, onCopyNodeKey, onFilterNodeType }) => {
  const canvasGraph = useMemo(() => selectCanvasGraph(graph, selectedNode), [graph, selectedNode])
  return (
    <div className="h-full min-h-0 bg-white">
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
