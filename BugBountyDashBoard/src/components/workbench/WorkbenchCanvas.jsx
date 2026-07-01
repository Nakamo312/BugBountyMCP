import React, { memo, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

const typeRank = {
  program: 0,
  host: 0,
  service: 1,
  route_family: 1,
  endpoint: 2,
  route_template: 2,
  param: 3,
  response_shape: 3,
  artifact_ref: 4,
  memory_fragment: 2,
  action_run: 2,
  research_hypothesis: 2,
  coverage_gap: 2,
}

const rankForNode = (node) => {
  if (Number.isFinite(node?.visual?.rank)) return node.visual.rank
  return typeRank[node?.node_type] ?? 2
}

const familyKey = (node) => {
  const properties = node?.properties || {}
  if (node?.node_type === 'host') return properties.host || node.label || 'host'
  if (node?.node_type === 'route_family') return `${properties.host || ''}:${properties.route_family || node.label}`
  const path = properties.route_template || properties.path || node.label || ''
  const host = properties.host || ''
  const first = String(path).replace(/^\//, '').split('/').filter(Boolean)[0] || '/'
  return `${host}:/${first}`
}

const nodePositionMap = (graph) => {
  const nodes = [...(graph?.nodes || [])]
  const groups = new Map()
  nodes.forEach((node) => {
    const rank = rankForNode(node)
    if (!groups.has(rank)) groups.set(rank, [])
    groups.get(rank).push(node)
  })

  const positions = new Map()
  const ranks = [...groups.keys()].sort((a, b) => a - b)
  ranks.forEach((rank) => {
    const ranked = groups.get(rank).sort((a, b) => {
      const family = familyKey(a).localeCompare(familyKey(b))
      return family || String(a.label).localeCompare(String(b.label))
    })
    const isDenseRank = ranked.length > 24
    const columnSize = isDenseRank ? 18 : Math.max(1, ranked.length)
    ranked.forEach((node, index) => {
      const localColumn = Math.floor(index / columnSize)
      const localRow = index % columnSize
      positions.set(node.id, {
        x: rank * 330 + localColumn * 250,
        y: localRow * 112,
      })
    })
  })
  return positions
}

const badgeClass = (badge) => {
  if (/^get|post|put|patch|delete$/i.test(badge)) return 'bg-primary-50 text-primary-700'
  if (/^2\d\d$/.test(String(badge))) return 'bg-green-50 text-green-700'
  if (/^4\d\d|^5\d\d/.test(String(badge))) return 'bg-orange-50 text-orange-700'
  if (String(badge) === 'ui-group') return 'bg-indigo-50 text-indigo-700'
  return 'bg-gray-100 text-gray-600'
}

const NodeMetaRow = ({ node }) => {
  const props = node.properties || {}
  if (node.node_type === 'host' || node.node_type === 'route_family') {
    return <span>{node.metrics?.surface_node_count || 0} surface nodes</span>
  }
  const bits = [props.method, props.status_code, props.content_type].filter(Boolean)
  return <span>{bits.join(' · ') || node.node_type}</span>
}

const WorkbenchNodeCard = memo(({ data }) => {
  const node = data.node
  const selected = data.selectedEntityKey === node.entity_key
  const isGroup = node.metadata?.ui_grouping || node.visual?.role === 'group'
  const cardClass = isGroup
    ? 'w-52 rounded-2xl border bg-indigo-50 p-3 shadow-sm'
    : 'w-48 rounded-xl border bg-white p-3 shadow-sm'
  const selectedClass = selected ? 'border-primary-500 ring-2 ring-primary-100' : isGroup ? 'border-indigo-200' : 'border-gray-200'
  return (
    <div className={`${cardClass} ${selectedClass}`}>
      <Handle type="target" position={Position.Left} className="!bg-gray-400" />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-gray-900" title={node.label}>{node.label}</div>
          <div className="mt-1 truncate text-xs text-gray-500" title={node.caption || node.entity_key}>{node.caption || node.entity_key}</div>
        </div>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${isGroup ? 'bg-indigo-600 text-white' : 'bg-gray-900 text-white'}`}>
          {isGroup ? 'group' : node.staleness || 'unknown'}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1">
        {(node.badges || []).slice(0, 5).map((badge) => (
          <span key={`${node.id}-${badge}`} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeClass(badge)}`}>
            {badge}
          </span>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-gray-500">
        <NodeMetaRow node={node} />
        <span>{node.evidence_refs?.length || 0} ev</span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-gray-400" />
    </div>
  )
})

WorkbenchNodeCard.displayName = 'WorkbenchNodeCard'

const nodeTypes = { workbenchNode: WorkbenchNodeCard }

const toFlowNodes = (graph, selectedEntityKey) => {
  const positions = nodePositionMap(graph)
  return (graph?.nodes || []).map((node) => ({
    id: node.id,
    type: 'workbenchNode',
    position: positions.get(node.id) || { x: 0, y: 0 },
    data: { node, selectedEntityKey },
  }))
}

const toFlowEdges = (graph) => (graph?.edges || []).map((edge) => ({
  id: edge.id,
  source: edge.source,
  target: edge.target,
  label: edge.label,
  data: { edge },
  animated: edge.delta_state === 'added' || edge.delta_state === 'changed',
  type: 'smoothstep',
}))

const EmptyCanvas = () => (
  <div className="flex h-full items-center justify-center rounded-xl border-2 border-dashed border-gray-200 bg-gray-50">
    <div className="text-center">
      <div className="text-sm font-semibold text-gray-700">No graph projection loaded</div>
      <div className="mt-1 text-sm text-gray-500">Use Workbench data setup to build the read model.</div>
    </div>
  </div>
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
      <div className="border-t border-gray-100 px-3 py-2 text-[11px] text-gray-500">
        Read-only menu. It does not submit actions, proposals, or graph mutations.
      </div>
    </div>
  )
}

const WorkbenchCanvas = ({ graph, selectedNode, onSelectNode, onFocusNode, onCopyNodeKey, onFilterNodeType }) => {
  const [contextMenu, setContextMenu] = useState(null)
  const selectedEntityKey = selectedNode?.entity_key
  const nodes = useMemo(() => toFlowNodes(graph, selectedEntityKey), [graph, selectedEntityKey])
  const edges = useMemo(() => toFlowEdges(graph), [graph])
  const nodeById = useMemo(() => new Map((graph?.nodes || []).map((node) => [node.id, node])), [graph])

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setContextMenu(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])

  if (!nodes.length) return <EmptyCanvas />

  const inspectNode = (node) => {
    if (node) onSelectNode(node)
  }
  const focusNode = (node) => {
    if (node) onFocusNode?.(node)
  }
  const copyNodeKey = (node) => {
    if (node?.entity_key) onCopyNodeKey?.(node.entity_key)
  }
  const filterNodeType = (node) => {
    if (node?.node_type) onFilterNodeType?.(node)
  }

  return (
    <>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.08}
        maxZoom={1.6}
        nodesDraggable
        onPaneClick={() => setContextMenu(null)}
        onMoveStart={() => setContextMenu(null)}
        onNodeClick={(_, flowNode) => inspectNode(nodeById.get(flowNode.id))}
        onNodeContextMenu={(event, flowNode) => {
          event.preventDefault()
          const node = nodeById.get(flowNode.id)
          if (!node) return
          setContextMenu({ node, x: event.clientX, y: event.clientY })
        }}
      >
        <Background gap={24} />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
      <GraphContextMenu
        menu={contextMenu}
        onClose={() => setContextMenu(null)}
        onInspect={inspectNode}
        onFocus={focusNode}
        onCopyKey={copyNodeKey}
        onFilterType={filterNodeType}
      />
    </>
  )
}

export default WorkbenchCanvas
