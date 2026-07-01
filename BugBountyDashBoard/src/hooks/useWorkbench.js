import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getWorkbenchBootstrap,
  getWorkbenchEntity,
  getWorkbenchEntityActions,
  getWorkbenchEntityMemory,
  getWorkbenchGraph,
  retrieveWorkbenchEvidence,
} from '../services/api'

const defaultLens = 'surface'

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

  const focusNode = useCallback((node) => {
    if (!node?.entity_key) return
    loadWorkbench({ nextLens: lens, seed: node.entity_key, depth: 2 })
  }, [lens, loadWorkbench])

  useEffect(() => {
    if (programId) {
      loadWorkbench({ nextLens: defaultLens })
    } else {
      setBootstrap(null)
      setGraph(null)
      setActiveSeed(null)
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
    reload: loadWorkbench,
    retrieveQuery,
    selectedNode,
    selectNode,
    setLens,
    setRetrieveQuery,
  }
}
