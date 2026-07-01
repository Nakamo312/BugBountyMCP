import { useCallback, useEffect, useRef, useState } from 'react'
import { getAgentActivity } from '../services/api'

const ACTIVITY_LIMIT = 50
const ACTIVITY_BUFFER_SIZE = 80
const POLL_INTERVAL_MS = 8000

const mergeEvents = (events, current) => {
  const seen = new Set()
  return [...events, ...current]
    .filter((event) => {
      const key = event.event_id || `${event.event_type}-${event.occurred_at}-${event.title}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, ACTIVITY_BUFFER_SIZE)
}

export function useAgentTaskActivity({ programId, taskId }) {
  const [activity, setActivity] = useState([])
  const activityCursorRef = useRef(null)

  const loadActivity = useCallback(async () => {
    if (!programId || !taskId) return
    try {
      const response = await getAgentActivity({
        program_id: programId,
        task_id: taskId,
        after: activityCursorRef.current || undefined,
        limit: ACTIVITY_LIMIT,
      })
      const events = response.data?.events || []
      if (events.length > 0) {
        setActivity((current) => mergeEvents(events, current))
      }
      activityCursorRef.current = response.data?.next_after || activityCursorRef.current
    } catch (err) {
      console.warn('Agent task activity polling failed:', err)
    }
  }, [programId, taskId])

  useEffect(() => {
    setActivity([])
    activityCursorRef.current = null
    if (!programId || !taskId) return undefined
    loadActivity()
    const interval = window.setInterval(loadActivity, POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [loadActivity, programId, taskId])

  return { activity, loadActivity }
}
