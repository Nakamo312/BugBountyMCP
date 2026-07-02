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

const defaultLens = 'surface'

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
  const [actionSubmission, setActionSubmission] = useState(null)
  const [actionSubmitting, setActionSubmitting] = useState(false)
  const [entityLoading, setEntityLoading] = useState(false)
  const [entityErrors, setEntityErrors] = useState({})
  const [error, setError] = useState(null)
  const [pendingSelectedEntity, setPendingSelectedEntity] = useState(null)
  const loadRequestRef = useRef(0)
  const selectionRequestRef = useRef(0)

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

  const unwrapSettled = (result) => (result.status === 'fulfilled' ? result.value?.data : null)

  const settledError = (result) => {
    if (result.status !== 'rejected') return null
    return result.reason?.response?.data?.detail || result.reason?.message || 'request failed'
  }

  const loadWorkbench = useCallback(async ({ nextLens = lens, seed = null, depth = seed ? 2 : 1, selected = null } = {}) => {
    if (!programId) return
    const requestId = loadRequestRef.current + 1
    loadRequestRef.current = requestId
    setLoading(true)
    setError(null)
    try {
      const [bootstrapResponse, graphResponse] = await Promise.all([
        getWorkbenchBootstrap(programId),
        getWorkbenchGraph({ programId, lens: nextLens, seed, depth }),
      ])
      if (requestId !== loadRequestRef.current) return
      setBootstrap(bootstrapResponse.data)
      setGraph(graphResponse.data)
      setLens(nextLens)
      setActiveSeed(seed)
      clearSelection()
      setPendingSelectedEntity(selected)
      writeWorkbenchRouteState({ lens: nextLens, seed, selected })
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
      setEntity(unwrapSettled(entityResponse))
      setActions(unwrapSettled(actionsResponse))
      setMemory(unwrapSettled(memoryResponse))
      setEvidencePack(unwrapSettled(evidencePackResponse))
      setActionSubmission(null)
      const errors = {
        profile: settledError(entityResponse),
        actions: settledError(actionsResponse),
        memory: settledError(memoryResponse),
        evidence: settledError(evidencePackResponse),
      }
      const visibleErrors = Object.fromEntries(Object.entries(errors).filter(([, value]) => value))
      setEntityErrors(visibleErrors)
      if (!unwrapSettled(entityResponse) && !unwrapSettled(actionsResponse) && !unwrapSettled(memoryResponse) && !unwrapSettled(evidencePackResponse)) {
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


  const submitSelectedAction = useCallback(async (action) => {
    if (!programId || !selectedNode?.entity_key || !action?.catalog_id) return null
    setActionSubmitting(true)
    setError(null)
    try {
      const response = await submitWorkbenchAction({
        programId,
        entityKey: selectedNode.entity_key,
        catalogId: action.catalog_id,
        entity: actionEntityFromNode(selectedNode),
        targets: action.inputs?.targets,
        options: action.prefilled_options || {},
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
      await loadWorkbench({ nextLens: lens, seed: activeSeed, depth: activeSeed ? 2 : 1 })
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

  useEffect(() => {
    if (programId) {
      const routeState = routeWorkbenchState()
      loadWorkbench({ nextLens: routeState.lens, seed: routeState.seed, depth: routeState.seed ? 2 : 1, selected: routeState.selected })
    } else {
      setBootstrap(null)
      setGraph(null)
      setActiveSeed(null)
      setProjectionResult(null)
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
