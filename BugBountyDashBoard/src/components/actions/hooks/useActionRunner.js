import { useState } from 'react'
import { createCatalogAction } from '@/services/api'

function compactOptions(values) {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== '' && value !== undefined && value !== null)
  )
}

export function useActionRunner(selectedProgram) {
  const [activeAction, setActiveAction] = useState(null)
  const [loading, setLoading] = useState(false)

  async function runAction(action, formData) {
    if (!selectedProgram) {
      return {
        status: 'error',
        message: 'No program selected',
        results: null,
      }
    }

    if (!action.catalogId && (!action.api || typeof action.api !== 'function')) {
      return {
        status: 'error',
        message: `Action ${action.id} is missing catalog metadata`,
        results: null,
      }
    }

    setLoading(true)
    setActiveAction(action.id)

    try {
      let response
      if (action.catalogId) {
        const { targets, ...rawOptions } = formData
        response = await createCatalogAction({
          catalog_id: action.catalogId,
          program_id: selectedProgram.id,
          targets: Array.isArray(targets) ? targets : [],
          options: compactOptions(rawOptions),
        })
      } else {
        response = await action.api({
          program_id: selectedProgram.id,
          ...formData,
        })
      }

      return {
        status: response.data.status,
        message: response.data.message,
        results: response.data.results,
      }
    } catch (err) {
      return {
        status: 'error',
        message: err.response?.data?.detail || err.message || 'Action failed',
        results: null,
      }
    } finally {
      setLoading(false)
      setActiveAction(null)
    }
  }

  return { runAction, activeAction, loading }
}

export default useActionRunner
