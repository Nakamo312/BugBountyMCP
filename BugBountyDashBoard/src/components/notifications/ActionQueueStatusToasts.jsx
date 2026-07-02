import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, X } from 'lucide-react'
import { useProgram } from '../../context/ProgramContext'
import { getCampaignWorkspace } from '../../services/api'

const POLL_MS = 8000
const MAX_TOASTS = 5
const MAX_STORED_TOASTS = 10

export function ActionQueueStatusToasts() {
  const { selectedProgram } = useProgram()
  const [notifications, setNotifications] = useState([])
  const queueStateRef = useRef(new Map())
  const readyRef = useRef(false)
  const requestSeqRef = useRef(0)
  const programId = selectedProgram?.id

  const dismiss = useCallback((id) => {
    setNotifications((current) => current.filter((item) => item.id !== id))
  }, [])

  const push = useCallback((items) => {
    if (!items.length) return
    setNotifications((current) => [...items, ...current].slice(0, MAX_STORED_TOASTS))
  }, [])

  const poll = useCallback(async () => {
    if (!programId) return
    const seq = requestSeqRef.current + 1
    requestSeqRef.current = seq
    try {
      const response = await getCampaignWorkspace({ program_id: programId })
      if (seq !== requestSeqRef.current) return
      const actions = response.data?.action_queue || []
      push(detectQueueTransitions(queueStateRef.current, actions, readyRef.current))
      queueStateRef.current = new Map(actions.map((action) => [String(action.action_id), queueStateSnapshot(action)]))
      readyRef.current = true
    } catch (error) {
      console.warn('Action queue status polling failed:', error)
    }
  }, [programId, push])

  useEffect(() => {
    queueStateRef.current = new Map()
    readyRef.current = false
    requestSeqRef.current += 1
    setNotifications([])
    if (!programId) return undefined
    poll()
    const interval = window.setInterval(poll, POLL_MS)
    return () => window.clearInterval(interval)
  }, [poll, programId])

  if (!notifications.length) return null
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-[100] flex w-[min(420px,calc(100vw-2rem))] flex-col gap-3">
      {notifications.slice(0, MAX_TOASTS).map((notification) => (
        <QueueStatusToast
          key={notification.id}
          notification={notification}
          onDismiss={dismiss}
        />
      ))}
    </div>
  )
}

function QueueStatusToast({ notification, onDismiss }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(notification.id), 7000)
    return () => window.clearTimeout(timer)
  }, [notification.id, onDismiss])

  const tone = toastToneClass(notification.tone)
  return (
    <article className={`pointer-events-auto rounded-2xl border bg-white p-4 shadow-2xl ${tone.border}`}>
      <div className="flex gap-3">
        <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${tone.icon}`}>
          <Bell size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-semibold text-gray-900">{notification.title}</p>
              <p className="mt-1 text-sm leading-5 text-gray-600">{notification.detail}</p>
            </div>
            <button
              type="button"
              onClick={() => onDismiss(notification.id)}
              className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              aria-label="Dismiss notification"
            >
              <X size={15} />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 font-medium text-gray-600">
              {notification.capabilityId}
            </span>
            <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 font-medium text-gray-600">
              {notification.profileId}
            </span>
            {notification.actionId && <span className="font-mono text-gray-400">#{shortId(notification.actionId)}</span>}
          </div>
        </div>
      </div>
    </article>
  )
}

function detectQueueTransitions(previousState, actions, ready) {
  const next = new Map(actions.map((action) => [String(action.action_id), queueStateSnapshot(action)]))
  if (!ready) return []

  const notifications = []
  actions.forEach((action) => {
    const actionId = String(action.action_id)
    const previous = previousState.get(actionId)
    const current = next.get(actionId)
    if (!previous) {
      notifications.push(notificationForNewAction(action, current))
      return
    }
    if (previous.key !== current.key) {
      notifications.push(notificationForTransition(action, previous, current))
    }
  })

  previousState.forEach((previous, actionId) => {
    if (!next.has(actionId)) notifications.push(notificationForRemovedAction(previous))
  })
  return notifications.filter(Boolean)
}

function queueStateSnapshot(action = {}) {
  const requestStatus = action.status || null
  const queueStage = action.queue_stage || null
  const dispatchStatus = action.dispatch_status || null
  const runStatus = action.run_status || null
  return {
    actionId: String(action.action_id || ''),
    capabilityId: action.capability_id || 'action',
    profileId: action.profile_id || 'default',
    requestStatus,
    queueStage,
    dispatchStatus,
    runStatus,
    key: [requestStatus, queueStage, dispatchStatus, runStatus].map((item) => item || '').join('|'),
  }
}

function notificationForNewAction(action, snapshot) {
  const needsApproval = snapshot.requestStatus === 'requires_approval'
  return buildNotification({
    action,
    snapshot,
    tone: needsApproval ? 'warning' : 'info',
    title: needsApproval ? 'Action needs approval' : 'Action entered queue',
    detail: action.queue_reason || `${snapshot.capabilityId} is waiting for execution.`,
  })
}

function notificationForTransition(action, previous, current) {
  if (current.runStatus === 'running') {
    return buildNotification({ action, snapshot: current, tone: 'info', title: 'Action started', detail: `${current.capabilityId} is running.` })
  }
  if (current.runStatus === 'flushing') {
    return buildNotification({ action, snapshot: current, tone: 'warning', title: 'Action output is being ingested', detail: `${current.capabilityId} finished execution and is flushing artifacts.` })
  }
  if (current.runStatus === 'failed' || current.runStatus === 'dead' || current.dispatchStatus === 'failed' || current.dispatchStatus === 'dead') {
    return buildNotification({
      action,
      snapshot: current,
      tone: 'error',
      title: 'Action failed',
      detail: action.run_error || action.dispatch_last_error || action.queue_reason || `${current.capabilityId} failed in the execution pipeline.`,
    })
  }
  if (current.requestStatus === 'requires_approval') {
    return buildNotification({ action, snapshot: current, tone: 'warning', title: 'Action needs approval', detail: action.queue_reason || `${current.capabilityId} is waiting for approval.` })
  }
  if (current.requestStatus === 'rejected') {
    return buildNotification({ action, snapshot: current, tone: 'warning', title: 'Action rejected or cancelled', detail: `${current.capabilityId} left the executable queue.` })
  }
  return buildNotification({
    action,
    snapshot: current,
    tone: 'neutral',
    title: 'Action status changed',
    detail: `${current.capabilityId}: ${formatQueueStatus(previous)} → ${formatQueueStatus(current)}`,
  })
}

function notificationForRemovedAction(previous) {
  return {
    id: `queue-removed-${previous.actionId}-${Date.now()}`,
    tone: previous.runStatus === 'failed' || previous.dispatchStatus === 'failed' ? 'error' : 'success',
    title: 'Action left active queue',
    detail: `${previous.capabilityId} completed, was cancelled, or moved to history.`,
    capabilityId: previous.capabilityId,
    profileId: previous.profileId,
    actionId: previous.actionId,
  }
}

function buildNotification({ action, snapshot, tone, title, detail }) {
  return {
    id: `queue-${snapshot.actionId}-${snapshot.key}-${Date.now()}`,
    tone,
    title,
    detail,
    capabilityId: snapshot.capabilityId,
    profileId: snapshot.profileId,
    actionId: snapshot.actionId || action.action_id,
  }
}

function formatQueueStatus(snapshot) {
  return snapshot.runStatus || snapshot.dispatchStatus || snapshot.queueStage || snapshot.requestStatus || 'unknown'
}

function shortId(value) {
  return String(value || '').slice(0, 8)
}

function toastToneClass(tone) {
  if (tone === 'success') return { border: 'border-emerald-200', icon: 'bg-emerald-50 text-emerald-700' }
  if (tone === 'warning') return { border: 'border-amber-200', icon: 'bg-amber-50 text-amber-700' }
  if (tone === 'error') return { border: 'border-red-200', icon: 'bg-red-50 text-red-700' }
  if (tone === 'info') return { border: 'border-blue-200', icon: 'bg-blue-50 text-blue-700' }
  return { border: 'border-gray-200', icon: 'bg-gray-50 text-gray-700' }
}
