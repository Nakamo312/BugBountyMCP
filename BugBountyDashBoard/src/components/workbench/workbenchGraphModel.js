const neo4jLens = (lens) => String(lens || '').startsWith('neo4j_')

export const nodeTypeLabel = (type) => ({
  program: 'Program',
  host: 'Host',
  service: 'Service',
  endpoint: 'Endpoint',
  route_family: 'Route family',
  route_template: 'Route template',
  param: 'Parameter',
  response_shape: 'Response shape',
  artifact_ref: 'Artifact',
  surface_component: 'Surface component',
  surface_component_graph_signal: 'Graph signal',
  surface_component_action_candidate: 'Action candidate',
  coverage_overview: 'Coverage overview',
  coverage_lane: 'Coverage lane',
  coverage_gap: 'Coverage gap',
  checked_entity: 'Checked entity',
  suggested_next_context: 'Suggested context',
  action_request: 'Action request',
  action_target: 'Action target',
  action_run: 'Action run',
  action_outcome: 'Action outcome',
  action_outcome_delta: 'Outcome delta',
  action_outcome_feedback: 'Outcome feedback',
  memory_fragment: 'Memory fragment',
  research_hypothesis: 'Hypothesis',
  research_signal: 'Research signal',
  neo4j_program: 'Neo4j Program',
  neo4j_scope: 'Neo4j Scope',
  neo4j_ip: 'Neo4j IP',
  neo4j_asn: 'Neo4j ASN',
  neo4j_cidr: 'Neo4j CIDR',
  neo4j_js_file: 'Neo4j JS file',
  neo4j_tool: 'Neo4j Tool',
  neo4j_tool_run: 'Neo4j Tool run',
  neo4j_action_outcome: 'Neo4j Action outcome',
  neo4j_capability_profile: 'Neo4j Capability/profile',
  neo4j_outcome_feature: 'Neo4j Outcome feature',
  neo4j_observation: 'Neo4j Observation',
  neo4j_evidence: 'Neo4j Evidence',
  neo4j_surface_snapshot: 'Neo4j Surface snapshot',
  neo4j_surface_node: 'Neo4j Surface node',
  neo4j_surface_fingerprint: 'Neo4j Fingerprint',
  neo4j_surface_delta: 'Neo4j Surface delta',
  neo4j_projection_status: 'Neo4j Projection status',
}[type] || String(type || 'entity').replaceAll('_', ' '))

export const lensLabel = (lens) => ({
  surface: 'Surface map',
  components: 'Surface components',
  memory: 'Outcome memory',
  hypothesis: 'Hypotheses',
  action: 'Action lifecycle',
  coverage: 'Coverage gaps',
  neo4j_exposure: 'Neo4j exposure',
  neo4j_endpoint: 'Neo4j endpoint',
  neo4j_evidence: 'Neo4j evidence',
  neo4j_surface_math: 'Neo4j surface math',
  neo4j_action_outcome: 'Neo4j outcomes',
  neo4j_js: 'Neo4j JS',
  neo4j_tech: 'Neo4j technology',
  neo4j_hypothesis: 'Neo4j hypotheses',
}[lens] || String(lens || 'Workbench'))

export const lensPurpose = (graph) => {
  const lens = graph?.lens
  if (lens === 'surface') return 'Current Surface Map snapshot: hosts, routes, endpoints, parameters, response shapes, and deltas from persisted observations.'
  if (lens === 'components') return 'Materialized Neo4j/GDS component analysis: pressure, drift, bridges, outliers, coverage, and candidate next actions.'
  if (lens === 'coverage') return 'Coverage read model: which structural entities have action experience, which remain unchecked, and where component signals suggest next context.'
  if (lens === 'action') return 'ActionService lifecycle: request, target, policy, approval, job, run, outcome, delta, and feedback links.'
  if (lens === 'memory') return 'Action-outcome memory: completed runs, artifacts, deltas, feedback, and utility traces used by future ranking.'
  if (lens === 'hypothesis') return 'Research hypothesis state: signals, evidence, score history, review state, and proposal links without promoting findings.'
  if (neo4jLens(lens)) return 'Allowlisted Neo4j graph-projector view. Reads ontology/projection relationships only; GDS and writes stay outside the request path.'
  return 'Backend-owned Workbench read model.'
}

export const toNumber = (value, fallback = 0) => {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

export const formatValue = (value) => {
  if (value == null || value === '') return 'n/a'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'none'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export const graphCounts = (graph) => {
  const counts = graph?.counts || {}
  const nodes = graph?.nodes || []
  const edges = graph?.edges || []
  return {
    nodes: counts.nodes ?? nodes.length,
    edges: counts.edges ?? edges.length,
    surfaceNodes: counts.surface_nodes ?? counts.snapshot_nodes_total,
    surfaceEdges: counts.surface_edges ?? counts.snapshot_edges_total,
    components: counts.surface_components ?? nodes.filter((node) => node.node_type === 'surface_component').length,
    proposals: counts.experience_proposals_pending,
    checked: counts.checked_entities,
    unchecked: counts.unchecked_entities,
    stale: counts.stale_entities,
    gaps: counts.component_gaps,
    neo4jRows: counts.neo4j_rows,
  }
}

export const nodeTypeGroups = (nodes = []) => {
  const groups = new Map()
  nodes.forEach((node) => {
    const type = node.node_type || 'entity'
    const current = groups.get(type) || { type, label: nodeTypeLabel(type), count: 0, actionCount: 0, evidenceCount: 0, fresh: 0, stale: 0 }
    current.count += 1
    current.actionCount += toNumber(node.action_affordance_count)
    current.evidenceCount += (node.evidence_refs || []).length
    if (node.staleness === 'fresh') current.fresh += 1
    if (node.staleness === 'stale') current.stale += 1
    groups.set(type, current)
  })
  return [...groups.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

export const relationshipGroups = (edges = []) => {
  const groups = new Map()
  edges.forEach((edge) => {
    const type = edge.relationship_type || edge.label || 'RELATED'
    const current = groups.get(type) || { type, label: String(edge.label || type).replaceAll('_', ' '), count: 0, changed: 0, weight: 0 }
    current.count += 1
    current.weight += toNumber(edge.weight, 1)
    if (['added', 'changed', 'removed'].includes(edge.delta_state)) current.changed += 1
    groups.set(type, current)
  })
  return [...groups.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

const metricValue = (node, key) => node?.metrics?.[key] ?? node?.properties?.[key] ?? node?.metadata?.metrics?.[key]

const signalScore = (node) => {
  const candidates = [
    metricValue(node, 'rank_signal'),
    metricValue(node, 'signal_score'),
    metricValue(node, 'structural_pressure_score'),
    metricValue(node, 'drift_score'),
    metricValue(node, 'bridge_pressure_score'),
    metricValue(node, 'outlier_score'),
    metricValue(node, 'coverage_score'),
    metricValue(node, 'exploration_priority_score'),
    metricValue(node, 'priority_score'),
    metricValue(node, 'utility_score'),
    metricValue(node, 'score'),
    toNumber(node?.confidence) * 100,
  ]
  for (const value of candidates) {
    const number = Number(value)
    if (Number.isFinite(number) && number !== 0) return number
  }
  return 0
}

export const nodeImportance = (node) => {
  let score = signalScore(node)
  score += toNumber(node?.metrics?.surface_node_count || node?.metrics?.node_count || node?.properties?.node_count) * 2
  score += toNumber(node?.metrics?.changed_node_count || node?.properties?.changed_node_count) * 8
  score += toNumber(node?.action_affordance_count) * 15
  score += (node?.evidence_refs || []).length * 4
  if ((node?.badges || []).some((badge) => String(badge).toLowerCase().includes('gap'))) score += 60
  if (String(node?.node_type || '').includes('gap')) score += 60
  if (node?.staleness === 'fresh') score += 5
  if (node?.staleness === 'stale') score += 15
  return score
}

export const importantNodes = (nodes = [], limit = 18) => [...nodes]
  .sort((a, b) => nodeImportance(b) - nodeImportance(a))
  .slice(0, limit)

export const selectedNeighborhood = (graph, selectedNode) => {
  if (!selectedNode) return { nodes: [], edges: [] }
  const selectedId = selectedNode.id
  const ids = new Set([selectedId])
  const edges = (graph?.edges || []).filter((edge) => {
    const hit = edge.source === selectedId || edge.target === selectedId
    if (hit) {
      ids.add(edge.source)
      ids.add(edge.target)
    }
    return hit
  })
  const nodes = (graph?.nodes || []).filter((node) => ids.has(node.id))
  return { nodes, edges }
}

export const businessSignals = (graph, selectedNode) => {
  const nodes = selectedNode ? selectedNeighborhood(graph, selectedNode).nodes : graph?.nodes || []
  const components = nodes.filter((node) => node.node_type === 'surface_component')
  const signalNodes = nodes.filter((node) => node.node_type === 'surface_component_graph_signal')
  const candidates = nodes.filter((node) => node.node_type === 'surface_component_action_candidate')
  const coverage = nodes.filter((node) => String(node.node_type || '').includes('coverage') || String(node.node_type || '').includes('gap'))
  const actionMemory = nodes.filter((node) => String(node.node_type || '').includes('outcome') || String(node.node_type || '').includes('action'))
  const neo4j = nodes.filter((node) => String(node.node_type || '').startsWith('neo4j_'))
  return [
    { id: 'components', label: 'Components', count: components.length, nodes: importantNodes(components, 5) },
    { id: 'signals', label: 'Graph signals', count: signalNodes.length, nodes: importantNodes(signalNodes, 5) },
    { id: 'candidates', label: 'Action candidates', count: candidates.length, nodes: importantNodes(candidates, 5) },
    { id: 'coverage', label: 'Coverage gaps', count: coverage.length, nodes: importantNodes(coverage, 5) },
    { id: 'memory', label: 'Action memory', count: actionMemory.length, nodes: importantNodes(actionMemory, 5) },
    { id: 'neo4j', label: 'Neo4j projection', count: neo4j.length, nodes: importantNodes(neo4j, 5) },
  ].filter((section) => section.count > 0)
}

export const readableNodeMetrics = (node) => {
  const merged = { ...(node?.properties || {}), ...(node?.metrics || {}) }
  const rows = [
    ['nodes', merged.surface_node_count ?? merged.node_count],
    ['changed', merged.changed_node_count],
    ['candidates', merged.action_candidate_count],
    ['rank', merged.rank_signal],
    ['signal', merged.signal_score],
    ['pressure', merged.structural_pressure_score],
    ['drift', merged.drift_score],
    ['bridge', merged.bridge_pressure_score],
    ['outlier', merged.outlier_score],
    ['coverage', merged.coverage_score],
    ['priority', merged.priority_score],
    ['gain', merged.information_gain_score ?? merged.utility_score],
    ['status', merged.status_code],
    ['port', merged.port],
  ]
  return rows.filter(([, value]) => value != null && value !== '')
}

export const buildLensStory = (graph, selectedNode) => {
  const counts = graphCounts(graph)
  const groups = nodeTypeGroups(graph?.nodes || [])
  const relationships = relationshipGroups(graph?.edges || [])
  const topGroup = groups[0]
  const topRelationship = relationships[0]
  const boundary = graph?.boundary || {}
  return [
    { label: 'Lens', value: lensLabel(graph?.lens) },
    { label: 'Source', value: boundary.surface || boundary.template || 'workbench read model' },
    { label: 'Graph', value: `${counts.nodes || 0} nodes / ${counts.edges || 0} edges` },
    topGroup ? { label: 'Dominant type', value: `${topGroup.label} (${topGroup.count})` } : null,
    topRelationship ? { label: 'Dominant edge', value: `${topRelationship.label} (${topRelationship.count})` } : null,
    selectedNode ? { label: 'Selected', value: `${nodeTypeLabel(selectedNode.node_type)} · ${selectedNode.label}` } : null,
  ].filter(Boolean)
}

export const frontendActionSeed = (node) => {
  if (!node) return null
  const values = node.action_target?.values || node.metadata?.action_bridge?.values || {}
  return values.url || values.hostname || values.address || values.cidr || values.asn || values.js_url || values.identity || node.canonical_entity_key || node.entity_key
}

export const lensSeed = (node, nextLens, activeSeed, bootstrap) => {
  if (nextLens === 'neo4j_surface_math') {
    return bootstrap?.projection_freshness?.latest_surface_snapshot?.snapshot_id || null
  }
  const seedRequired = String(nextLens || '').startsWith('neo4j_')
  if (!seedRequired) return null
  if (node?.entity_key?.startsWith('neo4j:')) return node.entity_key
  return node?.canonical_entity_key || node?.metadata?.identity_key || node?.action_target?.values?.identity || frontendActionSeed(node) || activeSeed || null
}
