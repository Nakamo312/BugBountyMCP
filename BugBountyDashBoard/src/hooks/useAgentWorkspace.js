import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  acceptActionExperienceProposal,
  acceptAgentActionProposal,
  appendAgentTaskMessage,
  approveAction,
  cancelAction,
  createAgentTask,
  getAgentActivity,
  getAgentTaskDetail,
  getCampaignWorkspace,
  rejectActionExperienceProposal,
  rejectAction,
  rejectAgentActionProposal,
  retryAcceptActionExperienceProposal,
  suppressActionExperienceProposal,
  suppressAgentActionProposal,
} from '../services/api'
import { useProgram } from '../context/ProgramContext'
import {
  buildAgentRuntimeMetadata,
  isDeepRuntimeMode,
} from '../components/agents/AgentRuntimeControls'
import {
  asExperienceProposalCard,
  isExperienceProposal,
  parseTargetList,
  proposalTargets,
} from '../components/agents/agentDisplay'

const emptyExperienceTargetReview = { proposalId: null, value: '', error: null }

export function useAgentWorkspace() {
  const { selectedProgram } = useProgram()
  const [workspace, setWorkspace] = useState(null)
  const [taskDetail, setTaskDetail] = useState(null)
  const [activity, setActivity] = useState([])
  const [activityCursor, setActivityCursor] = useState(null)
  const [selectedTaskId, setSelectedTaskId] = useState(null)
  const [prompt, setPrompt] = useState('')
  const [followup, setFollowup] = useState('')
  const [targetAgent, setTargetAgent] = useState('coordinator')
  const [runtimeMode, setRuntimeMode] = useState('none')
  const [deepConfirmed, setDeepConfirmed] = useState(false)
  const [followupRuntimeMode, setFollowupRuntimeMode] = useState('none')
  const [followupDeepConfirmed, setFollowupDeepConfirmed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [experienceTargetReview, setExperienceTargetReview] = useState(emptyExperienceTargetReview)
  const [error, setError] = useState(null)
  const [queueNotifications, setQueueNotifications] = useState([])
  const queueStateRef = useRef(new Map())
  const queueStateReadyRef = useRef(false)

  const programId = selectedProgram?.id

  const pushQueueNotifications = useCallback((items) => {
    if (!items.length) return
    setQueueNotifications((current) => [...items, ...current].slice(0, 8))
  }, [])

  const dismissQueueNotification = useCallback((notificationId) => {
    setQueueNotifications((current) => current.filter((item) => item.id !== notificationId))
  }, [])

  const trackQueueStatusChanges = useCallback((actions = []) => {
    const next = new Map(actions.map((action) => [String(action.action_id), queueStateSnapshot(action)]))
    if (!queueStateReadyRef.current) {
      queueStateRef.current = next
      queueStateReadyRef.current = true
      return
    }

    const notifications = []
    actions.forEach((action) => {
      const actionId = String(action.action_id)
      const previous = queueStateRef.current.get(actionId)
      const current = next.get(actionId)
      if (!previous) {
        notifications.push(queueNotificationForNewAction(action, current))
        return
      }
      if (previous.key !== current.key) {
        notifications.push(queueNotificationForTransition(action, previous, current))
      }
    })

    queueStateRef.current.forEach((previous, actionId) => {
      if (!next.has(actionId)) {
        notifications.push(queueNotificationForRemovedAction(previous))
      }
    })

    queueStateRef.current = next
    pushQueueNotifications(notifications.filter(Boolean))
  }, [pushQueueNotifications])

  const loadWorkspace = useCallback(async (options = {}) => {
    if (!programId) return
    const silent = Boolean(options.silent)
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    try {
      const response = await getCampaignWorkspace({ program_id: programId })
      const snapshot = response.data
      trackQueueStatusChanges(snapshot.action_queue || [])
      setWorkspace(snapshot)
      const firstTaskId = snapshot.tasks?.[0]?.task?.task_id
      setSelectedTaskId((current) => current || firstTaskId || null)
    } catch (err) {
      if (silent) {
        console.warn('Execution workspace polling failed:', err)
      } else {
        setError(err.response?.data?.detail || err.message || 'Failed to load execution workspace')
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [programId, trackQueueStatusChanges])

  const loadTaskDetail = useCallback(async (taskId) => {
    if (!taskId) {
      setTaskDetail(null)
      return
    }
    try {
      const response = await getAgentTaskDetail(taskId)
      setTaskDetail(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load task')
    }
  }, [])

  const loadActivity = useCallback(async () => {
    if (!programId) return
    try {
      const response = await getAgentActivity({
        program_id: programId,
        after: activityCursor || undefined,
        limit: 50,
      })
      const events = response.data?.events || []
      if (events.length > 0) {
        setActivity((current) => [...events, ...current].slice(0, 60))
        setActivityCursor(response.data.next_after || activityCursor)
        if (selectedTaskId) await loadTaskDetail(selectedTaskId)
      }
    } catch (err) {
      console.warn('Agent activity polling failed:', err)
    }
  }, [activityCursor, loadTaskDetail, programId, selectedTaskId])

  useEffect(() => {
    setWorkspace(null)
    setTaskDetail(null)
    setActivity([])
    setActivityCursor(null)
    setSelectedTaskId(null)
    setQueueNotifications([])
    queueStateRef.current = new Map()
    queueStateReadyRef.current = false
    loadWorkspace()
  }, [loadWorkspace])

  useEffect(() => {
    loadTaskDetail(selectedTaskId)
  }, [loadTaskDetail, selectedTaskId])

  useEffect(() => {
    if (!programId) return undefined
    const interval = window.setInterval(() => {
      loadActivity()
      loadWorkspace({ silent: true })
    }, 8000)
    return () => window.clearInterval(interval)
  }, [loadActivity, loadWorkspace, programId])

  const tasks = workspace?.tasks || []
  const taskCardsById = useMemo(() => new Map(tasks.map((card) => [card.task.task_id, card])), [tasks])
  const selectedTaskCard = selectedTaskId ? taskCardsById.get(selectedTaskId) : null
  const pendingProposals = workspace?.pending_agent_proposals || []
  const pendingExperienceProposals = useMemo(
    () => (workspace?.pending_experience_proposals || []).map(asExperienceProposalCard),
    [workspace?.pending_experience_proposals],
  )
  const rawMessages = taskDetail?.messages || selectedTaskCard?.messages || []
  const messages = useMemo(
    () => [...rawMessages].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0)),
    [rawMessages],
  )
  const proposals = taskDetail?.proposals || selectedTaskCard?.proposals || []
  const visibleProposals = [...proposals, ...pendingExperienceProposals, ...pendingProposals].slice(0, 6)

  const handleCreateTask = async (event) => {
    event.preventDefault()
    if (!programId || !prompt.trim()) return
    if (isDeepRuntimeMode(runtimeMode) && !deepConfirmed) return
    setActionBusy(true)
    setError(null)
    try {
      const response = await createAgentTask({
        program_id: programId,
        target_agent: targetAgent,
        prompt,
        created_by: 'human',
        source: 'ui',
        metadata: buildAgentRuntimeMetadata({
          mode: runtimeMode,
          deepConfirmed,
          uiSurface: 'campaign_workspace',
        }),
      })
      setPrompt('')
      setDeepConfirmed(false)
      const newTaskId = response.data?.task?.task_id
      await loadWorkspace()
      if (newTaskId) setSelectedTaskId(newTaskId)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to create task')
    } finally {
      setActionBusy(false)
    }
  }

  const handleFollowup = async (event) => {
    event.preventDefault()
    if (!selectedTaskId || !followup.trim()) return
    if (isDeepRuntimeMode(followupRuntimeMode) && !followupDeepConfirmed) return
    setActionBusy(true)
    setError(null)
    try {
      await appendAgentTaskMessage(selectedTaskId, {
        body: followup,
        created_by: 'human',
        source: 'ui',
        metadata: buildAgentRuntimeMetadata({
          mode: followupRuntimeMode,
          deepConfirmed: followupDeepConfirmed,
          uiSurface: 'agent_task_detail',
        }),
      })
      setFollowup('')
      setFollowupDeepConfirmed(false)
      await loadTaskDetail(selectedTaskId)
      await loadWorkspace()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to send message')
    } finally {
      setActionBusy(false)
    }
  }

  const reviewProposal = async (proposal, decision, options = {}) => {
    setActionBusy(true)
    setError(null)
    try {
      const applied = await applyProposalDecision(proposal, decision, options)
      if (!applied) return
      setExperienceTargetReview(emptyExperienceTargetReview)
      await loadWorkspace()
      if (selectedTaskId) await loadTaskDetail(selectedTaskId)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to apply decision')
    } finally {
      setActionBusy(false)
    }
  }

  const applyProposalDecision = async (proposal, decision, options) => {
    if (isExperienceProposal(proposal)) {
      return applyExperienceProposalDecision(proposal, decision, options)
    }
    await applyAgentProposalDecision(proposal, decision)
    return true
  }

  const applyExperienceProposalDecision = async (proposal, decision, options) => {
    if (decision === 'accept') {
      const targets = options.targets || []
      if (targets.length === 0) {
        setExperienceTargetReview((current) => ({
          ...current,
          proposalId: proposal.proposal_id,
          error: 'At least one target is required',
        }))
        return false
      }
      const retrying = proposal.status === 'accept_failed'
      const acceptCommand = retrying ? retryAcceptActionExperienceProposal : acceptActionExperienceProposal
      await acceptCommand(proposal.proposal_id, {
        accepted_by: 'human',
        reason: retrying ? 'Retried failed acceptance from campaign workspace UI' : 'Accepted from campaign workspace UI',
        targets,
        metadata: { ui_surface: 'campaign_workspace', boundary: 'experience_proposal_accept_to_action_service' },
      })
      return true
    }
    if (decision === 'reject') {
      await rejectActionExperienceProposal(proposal.proposal_id, {
        reviewed_by: 'human',
        reason: 'Rejected from campaign workspace UI',
        metadata: { ui_surface: 'campaign_workspace', feedback_tags: ['ui-reject'] },
      })
      return true
    }
    await suppressActionExperienceProposal(proposal.proposal_id, {
      reviewed_by: 'human',
      reason: 'Suppressed from campaign workspace UI',
      metadata: { ui_surface: 'campaign_workspace', feedback_tags: ['ui-suppress'] },
    })
    return true
  }

  const applyAgentProposalDecision = async (proposal, decision) => {
    if (decision === 'accept') {
      await acceptAgentActionProposal(proposal.proposal_id, {
        accepted_by: 'human',
        reason: 'Accepted from campaign workspace UI',
        metadata: { ui_surface: 'campaign_workspace' },
      })
      return
    }
    if (decision === 'reject') {
      await rejectAgentActionProposal(proposal.proposal_id, {
        reviewed_by: 'human',
        reason: 'Rejected from campaign workspace UI',
        feedback_tags: ['ui-reject'],
        metadata: { ui_surface: 'campaign_workspace' },
      })
      return
    }
    await suppressAgentActionProposal(proposal.proposal_id, {
      reviewed_by: 'human',
      reason: 'Suppressed from campaign workspace UI',
      feedback_tags: ['ui-suppress'],
      metadata: { ui_surface: 'campaign_workspace' },
    })
  }

  const beginAcceptProposal = (proposal) => {
    if (!isExperienceProposal(proposal)) {
      reviewProposal(proposal, 'accept')
      return
    }
    setExperienceTargetReview({
      proposalId: proposal.proposal_id,
      value: proposalTargets(proposal).join(', '),
      error: null,
    })
  }

  const submitExperienceTargets = (event, proposal) => {
    event.preventDefault()
    const targets = parseTargetList(experienceTargetReview.value)
    if (targets.length === 0) {
      setExperienceTargetReview((current) => ({ ...current, error: 'At least one target is required' }))
      return
    }
    reviewProposal(proposal, 'accept', { targets })
  }

  const reviewQueuedAction = async (action, decision) => {
    if (!action?.action_id) return
    setActionBusy(true)
    setError(null)
    try {
      if (decision === 'approve') {
        await approveAction(action.action_id, {
          approved_by: 'human',
          reason: 'Approved from campaign workspace action queue',
        })
      } else if (decision === 'cancel') {
        await cancelAction(action.action_id, {
          cancelled_by: 'human',
          reason: 'Cancelled from campaign workspace action queue',
        })
      } else {
        await rejectAction(action.action_id, {
          rejected_by: 'human',
          reason: 'Rejected from campaign workspace action queue',
        })
      }
      await loadWorkspace()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to review queued action')
    } finally {
      setActionBusy(false)
    }
  }

  return {
    selectedProgram,
    workspace,
    taskDetail,
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    selectedTaskCard,
    messages,
    visibleProposals,
    activity,
    prompt,
    setPrompt,
    followup,
    setFollowup,
    targetAgent,
    setTargetAgent,
    runtimeMode,
    setRuntimeMode,
    deepConfirmed,
    setDeepConfirmed,
    followupRuntimeMode,
    setFollowupRuntimeMode,
    followupDeepConfirmed,
    setFollowupDeepConfirmed,
    loading,
    actionBusy,
    experienceTargetReview,
    setExperienceTargetReview,
    error,
    queueNotifications,
    dismissQueueNotification,
    loadWorkspace,
    handleCreateTask,
    handleFollowup,
    beginAcceptProposal,
    reviewProposal,
    reviewQueuedAction,
    submitExperienceTargets,
  }
}


function queueStateSnapshot(action = {}) {
  const runStatus = action.run_status || null
  const dispatchStatus = action.dispatch_status || null
  const queueStage = action.queue_stage || null
  const requestStatus = action.status || null
  const effectiveStatus = runStatus || dispatchStatus || queueStage || requestStatus || 'unknown'
  return {
    actionId: String(action.action_id || ''),
    capabilityId: action.capability_id || 'action',
    profileId: action.profile_id || 'default',
    requestStatus,
    queueStage,
    dispatchStatus,
    runStatus,
    effectiveStatus,
    key: [requestStatus, queueStage, dispatchStatus, runStatus].map((item) => item || '').join('|'),
  }
}

function queueNotificationForNewAction(action, current) {
  return buildQueueNotification({
    action,
    snapshot: current,
    tone: current?.requestStatus === 'requires_approval' ? 'warning' : 'info',
    title: current?.requestStatus === 'requires_approval' ? 'Action needs approval' : 'Action entered queue',
    detail: action.queue_reason || `${current.capabilityId} is waiting for execution.`,
  })
}

function queueNotificationForTransition(action, previous, current) {
  const status = current.runStatus || current.dispatchStatus || current.queueStage || current.requestStatus
  if (current.runStatus === 'running') {
    return buildQueueNotification({ action, snapshot: current, tone: 'info', title: 'Action started', detail: `${current.capabilityId} is running.` })
  }
  if (current.runStatus === 'flushing') {
    return buildQueueNotification({ action, snapshot: current, tone: 'warning', title: 'Action output is being ingested', detail: `${current.capabilityId} finished execution and is flushing artifacts.` })
  }
  if (current.runStatus === 'failed' || current.runStatus === 'dead' || current.dispatchStatus === 'failed' || current.dispatchStatus === 'dead') {
    return buildQueueNotification({
      action,
      snapshot: current,
      tone: 'error',
      title: 'Action failed',
      detail: action.run_error || action.dispatch_last_error || action.queue_reason || `${current.capabilityId} failed in the execution pipeline.`,
    })
  }
  if (current.requestStatus === 'requires_approval') {
    return buildQueueNotification({ action, snapshot: current, tone: 'warning', title: 'Action needs approval', detail: action.queue_reason || `${current.capabilityId} is waiting for approval.` })
  }
  if (current.requestStatus === 'rejected') {
    return buildQueueNotification({ action, snapshot: current, tone: 'warning', title: 'Action rejected or cancelled', detail: `${current.capabilityId} left the executable queue.` })
  }
  return buildQueueNotification({
    action,
    snapshot: current,
    tone: status === 'running' ? 'info' : 'neutral',
    title: 'Action status changed',
    detail: `${current.capabilityId}: ${formatQueueStatus(previous)} → ${formatQueueStatus(current)}`,
  })
}

function queueNotificationForRemovedAction(previous) {
  return {
    id: `queue-removed-${previous.actionId}-${Date.now()}`,
    tone: previous.runStatus === 'failed' || previous.dispatchStatus === 'failed' ? 'error' : 'success',
    title: 'Action left active queue',
    detail: `${previous.capabilityId} completed, was cancelled, or moved to history.`,
    capabilityId: previous.capabilityId,
    profileId: previous.profileId,
    actionId: previous.actionId,
    createdAt: new Date().toISOString(),
  }
}

function buildQueueNotification({ action, snapshot, tone, title, detail }) {
  return {
    id: `queue-${snapshot.actionId}-${snapshot.key}-${Date.now()}`,
    tone,
    title,
    detail,
    capabilityId: snapshot.capabilityId,
    profileId: snapshot.profileId,
    actionId: snapshot.actionId,
    createdAt: new Date().toISOString(),
  }
}

function formatQueueStatus(snapshot) {
  return snapshot.runStatus || snapshot.dispatchStatus || snapshot.queueStage || snapshot.requestStatus || 'unknown'
}
