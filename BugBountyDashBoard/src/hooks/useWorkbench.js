import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getWorkbenchBootstrap,
  getWorkbenchEntity,
  getWorkbenchAvailableActions,
  getWorkbenchEntityMemory,
  getWorkbenchGraph,
  retrieveWorkbenchEvidence,
  runWorkbenchProjectionRefresh,
  submitWorkbenchAction,
} from '../services/api'
import { lensSeed } from '../components/workbench/workbenchGraphModel'

const defaultLens = 'surface'

const neo4jLens = (value) => String(value || '').startsWith('neo4j_')

const settledData = (result) => (result.status === 'fulfilled' ? result.value?.data : null)

const settledMessage = (result) => {
  if (result.status !== 'rejected') return null
  return result.reason?.response?.data?.detail || result.reason?.message || 'request failed'
}

const fetchWorkbenchState = async ({ programId, nextLens, seed, depth }) => {
  const [bootstrapResult, graphResult] = await Promise.allSettled([
    getWorkbenchBootstrap(programId),
    getWorkbenchGraph({ programId, lens: nextLens, seed, depth }),
  ])
  const bootstrap = settledData(bootstrapResult)
  const graph = settledData(graphResult)
  const bootstrapError = settledMessage(bootstrapResult)
  const graphError = settledMessage(graphResult)
  if (!bootstrap && !graph) {
    throw new Error(graphError || bootstrapError || 'Failed to load workbench')
  }
  return { bootstrap, graph, error: graphError || bootstrapError }
}

const queueHasWork = (queue) => {
  if (!queue || typeof queue !== 'object') return false
  return Object.values(queue).some((stats) => (
    stats && typeof stats === 'object' && ((stats.pending || 0) > 0 || (stats.locked || 0) > 0)
  ))
}

const projectionRepairPlan = ({ nextLens, seed, graph, bootstrap, error }) => {
  const freshness = bootstrap?.projection_freshness || {}
  const queueHealth = bootstrap?.queue_health || {}
  const status = graph?.boundary?.status
  const reason = graph?.boundary?.reason || error || null
  const graphEmpty = !graph || (graph.nodes || []).length === 0
  const hasSnapshot = Boolean(freshness.latest_surface_snapshot)
  const hasAnalysis = Boolean(freshness.latest_surface_analysis)

  if (neo4jLens(nextLens)) {
    if (status === 'seed_required' || (!seed && ['neo4j_endpoint', 'neo4j_evidence', 'neo4j_surface_math'].includes(nextLens))) {
      return null
    }
    if (status === 'empty' || status === 'unavailable' || graphEmpty || queueHasWork({ graph_projection_events: queueHealth.graph_projection_events, graph_fact_batches: queueHealth.graph_fact_batches })) {
      return { operation: 'sync_neo4j', reason: reason || 'neo4j_projection_not_ready' }
    }
    return null
  }

  if (nextLens === 'components') {
    if (!hasSnapshot || !hasAnalysis || graphEmpty || /component graph not found/i.test(error || '')) {
      return { operation: 'refresh_workbench', reason: reason || 'surface_components_not_ready' }
    }
    return null
  }

  if (nextLens === 'surface' || nextLens === 'coverage') {
    if (!hasSnapshot || graphEmpty || /surface graph not found|coverage graph not found/i.test(error || '')) {
      return { operation: 'build_surface', reason: reason || 'surface_projection_not_ready' }
    }
    if (freshness.ui_data_fresh === false || freshness.surface_analysis_fresh === false || freshness.search_index_fresh === false) {
      return { operation: 'refresh_workbench', reason: 'workbench_read_models_stale' }
    }
  }

  return null
}

const routeWorkbenchState = () => {
  if (typeof window === 'undefined') return { lens: defaultLens, seed: null, selected: null }
  const params = new URLSearchParams(window.location.search)
  return {
    lens: params.get('lens') || defaultLens,
    seed: params.get('seed') || null,
    selected: params.get('selected') || null,
  }
}

const writeWorkbenchRouteState = ({ lens, seed, selected }) => {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  params.set('lens', lens || defaultLens)
  if (seed) params.set('seed', seed)
  else params.delete('seed')
  if (selected) params.set('selected', selected)
  else params.delete('selected')
  const next = `${window.location.pathname}?${params.toString()}`
  window.history.replaceState({}, '', next)
}

export const useWorkbench = (selectedProgram) => {
  const [lens, setLens] = useState(defaultLens)
  const [bootstrap, setBootstrap] = useState(null)
  const [graph, setGraph] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [entity, setEntity] = useState(null)
  const [actions, setActions] = useState(null)
  const [memory, setMemory] = useState(null)
  const [evidencePack, setEvidencePack] = useState(null)
  const [retrieveQuery, setRetrieveQuery] = useState('')
  const [activeSeed, setActiveSeed] = useState(null)
  const [loading, setLoading] = useState(false)
  const [projectionRunning, setProjectionRunning] = useState(false)
  const [projectionResult, setProjectionResult] = useState(null)
  const [autoProjection, setAutoProjection] = useState(null)
  const [actionSubmission, setActionSubmission] = useState(null)
  const [actionSubmitting, setActionSubmitting] = useState(false)
  const [entityLoading, setEntityLoading] = useState(false)
  const [entityErrors, setEntityErrors] = useState({})
  const [error, setError] = useState(null)
  const [pendingSelectedEntity, setPendingSelectedEntity] = useState(null)
  const loadRequestRef = useRef(0)
  const selectionRequestRef = useRef(0)
  const autoProjectionAttemptsRef = useRef(new Set())

  const programId = selectedProgram?.id

  const clearSelection = useCallback(() => {
    setSelectedNode(null)
    setEntity(null)
    setActions(null)
    setMemory(null)
    setEvidencePack(null)
    setActionSubmission(null)
    setEntityErrors({})
  }, [])

  const actionEntityFromNode = useCallback((node) => ({
    source: node?.metadata?.projection_source || node?.source_projection || 'workbench_graph',
    label: node?.node_type || node?.metadata?.labels?.[0] || null,
    entity_key: node?.entity_key || null,
    properties: {
      ...(node?.action_target?.values || {}),
      ...(node?.action_target || {}),
      ...(node?.properties || {}),
    },
    metadata: {
      ...(node?.metadata || {}),
      canonical_entity_key: node?.canonical_entity_key || node?.metadata?.canonical_entity_key || null,
      action_target: node?.action_target || null,
      display: node?.label || null,
      labels: node?.metadata?.labels || [],
      node_type: node?.node_type || null,
    },
  }), [])


  const loadWorkbench = useCallback(async ({ nextLens = lens, seed = null, depth = seed ? 2 : 1, selected = null, autoRepair = true } = {}) => {
    if (!programId) return
    const requestId = loadRequestRef.current + 1
    loadRequestRef.current = requestId
    setLoading(true)
    setError(null)
    try {
      const state = await fetchWorkbenchState({ programId, nextLens, seed, depth })
      if (requestId !== loadRequestRef.current) return

      const repair = autoRepair ? projectionRepairPlan({
        nextLens,
        seed,
        graph: state.graph,
        bootstrap: state.bootstrap,
        error: state.error,
      }) : null
      const repairKey = repair ? `${programId}:${nextLens}:${seed || 'root'}:${repair.operation}:${repair.reason || 'repair'}` : null
      if (repair && !autoProjectionAttemptsRef.current.has(repairKey)) {
        autoProjectionAttemptsRef.current.add(repairKey)
        setAutoProjection({ operation: repair.operation, reason: repair.reason, lens: nextLens, seed })
        setProjectionRunning(true)
        try {
          const response = await runWorkbenchProjectionRefresh({
            program_id: programId,
            operation: repair.operation,
          })
          if (requestId !== loadRequestRef.current) return
          setProjectionResult(response.data)
          const refreshed = await fetchWorkbenchState({ programId, nextLens, seed, depth })
          if (requestId !== loadRequestRef.current) return
          state.bootstrap = refreshed.bootstrap || state.bootstrap
          state.graph = refreshed.graph
          state.error = refreshed.error
        } catch (projectionError) {
          if (requestId !== loadRequestRef.current) return
          setProjectionResult(null)
          state.error = projectionError.response?.data?.detail || projectionError.message || 'Failed to auto-build Workbench projection'
        } finally {
          if (requestId === loadRequestRef.current) {
            setProjectionRunning(false)
            setAutoProjection(null)
          }
        }
      }

      setBootstrap(state.bootstrap)
      setGraph(state.graph)
      setLens(nextLens)
      setActiveSeed(seed)
      clearSelection()
      setPendingSelectedEntity(selected)
      writeWorkbenchRouteState({ lens: nextLens, seed, selected })
      setError(state.error && !state.graph ? state.error : null)
    } catch (err) {
      if (requestId !== loadRequestRef.current) return
      setGraph(null)
      setError(err.response?.data?.detail || err.message || 'Failed to load workbench')
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false)
    }
  }, [clearSelection, lens, programId])

  const selectNode = useCallback(async (node) => {
    if (!programId || !node?.entity_key) return
    const requestId = selectionRequestRef.current + 1
    selectionRequestRef.current = requestId
    setSelectedNode(node)
    writeWorkbenchRouteState({ lens, seed: activeSeed, selected: node.entity_key })
    setEntityLoading(true)
    setError(null)
    setEntityErrors({})
    try {
      const [entityResponse, actionsResponse, memoryResponse, evidencePackResponse] = await Promise.allSettled([
        getWorkbenchEntity(programId, node.entity_key),
        getWorkbenchAvailableActions({ programId, entityKey: node.entity_key, entity: actionEntityFromNode(node), lens }),
        getWorkbenchEntityMemory(programId, node.entity_key),
        retrieveWorkbenchEvidence({
          program_id: programId,
          selected_entities: [node.entity_key],
          lens,
          query: retrieveQuery.trim() || undefined,
        }),
      ])
      if (requestId !== selectionRequestRef.current) return
      setEntity(settledData(entityResponse))
      setActions(settledData(actionsResponse))
      setMemory(settledData(memoryResponse))
      setEvidencePack(settledData(evidencePackResponse))
      setActionSubmission(null)
      const errors = {
        profile: settledMessage(entityResponse),
        actions: settledMessage(actionsResponse),
        memory: settledMessage(memoryResponse),
        evidence: settledMessage(evidencePackResponse),
      }
      const visibleErrors = Object.fromEntries(Object.entries(errors).filter(([, value]) => value))
      setEntityErrors(visibleErrors)
      if (!settledData(entityResponse) && !settledData(actionsResponse) && !settledData(memoryResponse) && !settledData(evidencePackResponse)) {
        setError('Failed to load selected entity context')
      }
    } catch (err) {
      if (requestId !== selectionRequestRef.current) return
      setEntity(null)
      setActions(null)
      setMemory(null)
      setEvidencePack(null)
      setActionSubmission(null)
      setEntityErrors({ selection: err.response?.data?.detail || err.message || 'Failed to load entity' })
      setError(err.response?.data?.detail || err.message || 'Failed to load entity')
    } finally {
      if (requestId === selectionRequestRef.current) setEntityLoading(false)
    }
  }, [actionEntityFromNode, activeSeed, lens, programId, retrieveQuery])


  const submitSelectedAction = useCallback(async (action, override = {}) => {
    if (!programId || !selectedNode?.entity_key || !action?.catalog_id) return null
    const targets = override.targets || action.submit_payload?.targets || action.inputs?.targets || []
    const options = override.options || action.prefilled_options || {}
    setActionSubmitting(true)
    setError(null)
    try {
      const response = await submitWorkbenchAction({
        programId,
        entityKey: selectedNode.entity_key,
        catalogId: action.catalog_id,
        entity: actionEntityFromNode(selectedNode),
        targets,
        options,
        lens,
      })
      setActionSubmission(response.data)
      const actionsResponse = await getWorkbenchAvailableActions({
        programId,
        entityKey: selectedNode.entity_key,
        entity: actionEntityFromNode(selectedNode),
        lens,
      })
      setActions(actionsResponse.data)
      return response.data
    } catch (err) {
      setActionSubmission(null)
      setError(err.response?.data?.detail || err.message || 'Failed to submit Workbench action')
      return null
    } finally {
      setActionSubmitting(false)
    }
  }, [actionEntityFromNode, lens, programId, selectedNode])


  const runProjectionRefresh = useCallback(async (operation = 'refresh_workbench') => {
    if (!programId) return null
    setProjectionRunning(true)
    setError(null)
    try {
      const response = await runWorkbenchProjectionRefresh({
        program_id: programId,
        operation,
      })
      setProjectionResult(response.data)
      await loadWorkbench({ nextLens: lens, seed: activeSeed, depth: activeSeed ? 2 : 1, autoRepair: false })
      return response.data
    } catch (err) {
      setProjectionResult(null)
      setError(err.response?.data?.detail || err.message || 'Failed to refresh workbench projections')
      return null
    } finally {
      setProjectionRunning(false)
    }
  }, [activeSeed, lens, loadWorkbench, programId])

  const focusNode = useCallback((node) => {
    if (!node?.entity_key) return
    loadWorkbench({ nextLens: lens, seed: node.entity_key, depth: 2 })
  }, [lens, loadWorkbench])


  const seedForLens = useCallback((nextLens) => {
    const descriptor = (bootstrap?.lenses || []).find((item) => item.lens === nextLens)
    if (!descriptor?.seed_required && !String(nextLens || '').startsWith('neo4j_')) return null
    return lensSeed(selectedNode, nextLens, activeSeed, bootstrap)
  }, [activeSeed, bootstrap, selectedNode])

  const openLens = useCallback((nextLens) => {
    const seed = seedForLens(nextLens)
    loadWorkbench({ nextLens, seed, depth: seed ? 2 : 1 })
  }, [loadWorkbench, seedForLens])

  useEffect(() => {
    if (programId) {
      const routeState = routeWorkbenchState()
      loadWorkbench({ nextLens: routeState.lens, seed: routeState.seed, depth: routeState.seed ? 2 : 1, selected: routeState.selected })
    } else {
      setBootstrap(null)
      setGraph(null)
      setActiveSeed(null)
      setProjectionResult(null)
      setAutoProjection(null)
      autoProjectionAttemptsRef.current = new Set()
      clearSelection()
      setError(null)
    }
  }, [programId]) // eslint-disable-line react-hooks/exhaustive-deps


  useEffect(() => {
    if (!pendingSelectedEntity || !graph?.nodes?.length) return
    const node = graph.nodes.find((item) => item.entity_key === pendingSelectedEntity || item.id === pendingSelectedEntity)
    if (!node) return
    setPendingSelectedEntity(null)
    selectNode(node)
  }, [graph, pendingSelectedEntity, selectNode])

  const lenses = useMemo(() => bootstrap?.lenses || [], [bootstrap])

  return {
    actionSubmission,
    autoProjection,
    actionSubmitting,
    actions,
    activeSeed,
    bootstrap,
    entity,
    entityErrors,
    entityLoading,
    error,
    evidencePack,
    focusNode,
    graph,
    lens,
    lenses,
    loading,
    memory,
    projectionResult,
    projectionRunning,
    openLens,
    reload: loadWorkbench,
    retrieveQuery,
    runProjectionRefresh,
    selectedNode,
    submitSelectedAction,
    selectNode,
    setLens,
    setRetrieveQuery,
  }
}
