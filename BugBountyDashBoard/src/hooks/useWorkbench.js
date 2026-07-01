import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getWorkbenchBootstrap,
  getWorkbenchEntity,
  getWorkbenchEntityActions,
  getWorkbenchEntityMemory,
  getWorkbenchGraph,
  retrieveWorkbenchEvidence,
  runWorkbenchProjectionRefresh,
} from '../services/api'

const defaultLens = 'surface'

const routeWorkbenchState = () => {
  if (typeof window === 'undefined') return { lens: defaultLens, seed: null }
  const params = new URLSearchParams(window.location.search)
  return {
    lens: params.get('lens') || defaultLens,
    seed: params.get('seed') || null,
  }
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
  const [entityLoading, setEntityLoading] = useState(false)
  const [error, setError] = useState(null)

  const programId = selectedProgram?.id

  const clearSelection = useCallback(() => {
    setSelectedNode(null)
    setEntity(null)
    setActions(null)
    setMemory(null)
    setEvidencePack(null)
  }, [])

  const loadWorkbench = useCallback(async ({ nextLens = lens, seed = null, depth = seed ? 2 : 1 } = {}) => {
    if (!programId) return
    setLoading(true)
    setError(null)
    try {
      const [bootstrapResponse, graphResponse] = await Promise.all([
        getWorkbenchBootstrap(programId),
        getWorkbenchGraph({ programId, lens: nextLens, seed, depth }),
      ])
      setBootstrap(bootstrapResponse.data)
      setGraph(graphResponse.data)
      setLens(nextLens)
      setActiveSeed(seed)
      clearSelection()
    } catch (err) {
      setGraph(null)
      setError(err.response?.data?.detail || err.message || 'Failed to load workbench')
    } finally {
      setLoading(false)
    }
  }, [clearSelection, lens, programId])

  const selectNode = useCallback(async (node) => {
    if (!programId || !node?.entity_key) return
    setSelectedNode(node)
    setEntityLoading(true)
    setError(null)
    try {
      const [entityResponse, actionsResponse, memoryResponse, evidencePackResponse] = await Promise.all([
        getWorkbenchEntity(programId, node.entity_key),
        getWorkbenchEntityActions(programId, node.entity_key),
        getWorkbenchEntityMemory(programId, node.entity_key),
        retrieveWorkbenchEvidence({
          program_id: programId,
          selected_entities: [node.entity_key],
          lens,
          query: retrieveQuery.trim() || undefined,
        }),
      ])
      setEntity(entityResponse.data)
      setActions(actionsResponse.data)
      setMemory(memoryResponse.data)
      setEvidencePack(evidencePackResponse.data)
    } catch (err) {
      setEntity(null)
      setActions(null)
      setMemory(null)
      setEvidencePack(null)
      setError(err.response?.data?.detail || err.message || 'Failed to load entity')
    } finally {
      setEntityLoading(false)
    }
  }, [lens, programId, retrieveQuery])


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
      loadWorkbench({ nextLens: routeState.lens, seed: routeState.seed, depth: routeState.seed ? 2 : 1 })
    } else {
      setBootstrap(null)
      setGraph(null)
      setActiveSeed(null)
      setProjectionResult(null)
      clearSelection()
      setError(null)
    }
  }, [programId]) // eslint-disable-line react-hooks/exhaustive-deps

  const lenses = useMemo(() => bootstrap?.lenses || [], [bootstrap])

  return {
    actions,
    activeSeed,
    bootstrap,
    entity,
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
    selectNode,
    setLens,
    setRetrieveQuery,
  }
}
