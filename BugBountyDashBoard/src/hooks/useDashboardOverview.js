import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getHostsByProgram,
  getProgramProjectionOperatorPlan,
  getProgramProjectionOverview,
  healthCheck,
} from '../services/api'

const emptyDashboardState = {
  healthStatus: null,
  hostsCount: 0,
  loading: true,
  operatorPlan: null,
  overview: null,
  overviewError: null,
  overviewLoading: false,
}

const projectionOverviewErrorMessage = (error) => {
  if (error.response?.status === 404) return 'No projection state has been recorded for this program yet.'
  return error.response?.data?.detail || error.message || 'Failed to load projection overview'
}

export const useDashboardOverview = (selectedProgram) => {
  const [state, setState] = useState(emptyDashboardState)
  const patchState = useCallback((patch) => setState((current) => ({ ...current, ...patch })), [])

  const checkHealth = useCallback(async () => {
    try {
      await healthCheck()
      patchState({ healthStatus: 'healthy' })
    } catch (error) {
      patchState({ healthStatus: 'unhealthy' })
    } finally {
      patchState({ loading: false })
    }
  }, [patchState])

  const loadHostsCount = useCallback(async () => {
    if (!selectedProgram) return
    try {
      const response = await getHostsByProgram(selectedProgram.id, { limit: 1 })
      patchState({ hostsCount: response.data.total || 0 })
    } catch (error) {
      console.error('Failed to load hosts count:', error)
    }
  }, [patchState, selectedProgram])

  const loadProjectionOverview = useCallback(async () => {
    if (!selectedProgram) return
    patchState({ overviewError: null, overviewLoading: true })
    try {
      const [overviewResponse, planResponse] = await Promise.all([
        getProgramProjectionOverview(selectedProgram.id),
        getProgramProjectionOperatorPlan(selectedProgram.id),
      ])
      patchState({ operatorPlan: planResponse.data, overview: overviewResponse.data })
    } catch (error) {
      patchState({ operatorPlan: null, overview: null, overviewError: projectionOverviewErrorMessage(error) })
    } finally {
      patchState({ overviewLoading: false })
    }
  }, [patchState, selectedProgram])

  useEffect(() => {
    checkHealth()
  }, [checkHealth])

  useEffect(() => {
    if (!selectedProgram) {
      patchState({ hostsCount: 0, operatorPlan: null, overview: null, overviewError: null })
      return
    }
    loadHostsCount()
    loadProjectionOverview()
  }, [loadHostsCount, loadProjectionOverview, patchState, selectedProgram])

  const programSummary = useMemo(() => {
    if (!selectedProgram) return 'Select a program to start working.'
    if (state.overview?.ui_data_fresh) return 'Projection pipeline is fresh.'
    if (state.overview) return 'Projection pipeline needs attention.'
    return 'Projection pipeline status is unavailable.'
  }, [selectedProgram, state.overview])

  return { ...state, loadProjectionOverview, programSummary }
}
