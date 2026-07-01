import { useCallback, useEffect, useMemo, useState } from 'react'
import { getAgentTaskDetail } from '../services/api'

const DETAIL_LIMITS = {
  message_limit: 200,
  proposal_limit: 100,
  outcome_limit: 30,
}

const taskDetailError = (err) => err.response?.data?.detail || err.message || 'Не удалось загрузить задачу'

export function useAgentTaskDetail(taskId) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadDetail = useCallback(async () => {
    if (!taskId) return
    setLoading(true)
    setError(null)
    try {
      const response = await getAgentTaskDetail(taskId, DETAIL_LIMITS)
      setDetail(response.data)
    } catch (err) {
      setError(taskDetailError(err))
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    setDetail(null)
    loadDetail()
  }, [loadDetail])

  const sortedMessages = useMemo(
    () => [...(detail?.messages || [])].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0)),
    [detail?.messages],
  )

  return {
    detail,
    error,
    loading,
    reloadDetail: loadDetail,
    setError,
    sortedMessages,
  }
}
