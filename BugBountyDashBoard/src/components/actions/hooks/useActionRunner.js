import { useState } from 'react'

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

    if (!action.api || typeof action.api !== 'function') {
      return {
        status: 'error',
        message: `API function not defined for action ${action.id}`,
        results: null,
      }
    }

    setLoading(true)
    setActiveAction(action.id)

    try {
      const response = await action.api({
        program_id: selectedProgram.id,
        ...formData,
      })

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
