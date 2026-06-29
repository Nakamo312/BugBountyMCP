import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  acceptActionExperienceProposal,
  acceptAgentActionProposal,
  appendAgentTaskMessage,
  createAgentTask,
  getAgentActivity,
  getAgentTaskDetail,
  getCampaignWorkspace,
  rejectActionExperienceProposal,
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

  const programId = selectedProgram?.id

  const loadWorkspace = useCallback(async () => {
    if (!programId) return
    setLoading(true)
    setError(null)
    try {
      const response = await getCampaignWorkspace({ program_id: programId })
      const snapshot = response.data
      setWorkspace(snapshot)
      const firstTaskId = snapshot.tasks?.[0]?.task?.task_id
      setSelectedTaskId((current) => current || firstTaskId || null)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Не удалось загрузить рабочее пространство')
    } finally {
      setLoading(false)
    }
  }, [programId])

  const loadTaskDetail = useCallback(async (taskId) => {
    if (!taskId) {
      setTaskDetail(null)
      return
    }
    try {
      const response = await getAgentTaskDetail(taskId)
      setTaskDetail(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Не удалось загрузить задачу')
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
        await loadWorkspace()
        if (selectedTaskId) await loadTaskDetail(selectedTaskId)
      }
    } catch (err) {
      console.warn('Agent activity polling failed:', err)
    }
  }, [activityCursor, loadTaskDetail, loadWorkspace, programId, selectedTaskId])

  useEffect(() => {
    setWorkspace(null)
    setTaskDetail(null)
    setActivity([])
    setActivityCursor(null)
    setSelectedTaskId(null)
    loadWorkspace()
  }, [loadWorkspace])

  useEffect(() => {
    loadTaskDetail(selectedTaskId)
  }, [loadTaskDetail, selectedTaskId])

  useEffect(() => {
    if (!programId) return undefined
    const interval = window.setInterval(() => {
      loadActivity()
    }, 8000)
    return () => window.clearInterval(interval)
  }, [loadActivity, programId])

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
      setError(err.response?.data?.detail || err.message || 'Не удалось создать задачу')
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
      setError(err.response?.data?.detail || err.message || 'Не удалось отправить сообщение')
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
      setError(err.response?.data?.detail || err.message || 'Не удалось применить решение')
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
          error: 'Нужно указать хотя бы один target',
        }))
        return false
      }
      const retrying = proposal.status === 'accept_failed'
      const acceptCommand = retrying ? retryAcceptActionExperienceProposal : acceptActionExperienceProposal
      await acceptCommand(proposal.proposal_id, {
        accepted_by: 'human',
        reason: retrying ? 'Retried failed acceptance from campaign workspace UI' : 'Accepted from campaign workspace UI',
        confidence: 0.6,
        targets,
        metadata: { ui_surface: 'campaign_workspace', boundary: 'experience_proposal_accept_to_action_service' },
      })
      return true
    }
    if (decision === 'reject') {
      await rejectActionExperienceProposal(proposal.proposal_id, {
        reviewed_by: 'human',
        reason: 'Rejected from campaign workspace UI',
        confidence: 0.7,
        metadata: { ui_surface: 'campaign_workspace', feedback_tags: ['ui-reject'] },
      })
      return true
    }
    await suppressActionExperienceProposal(proposal.proposal_id, {
      reviewed_by: 'human',
      reason: 'Suppressed from campaign workspace UI',
      confidence: 0.8,
      metadata: { ui_surface: 'campaign_workspace', feedback_tags: ['ui-suppress'] },
    })
    return true
  }

  const applyAgentProposalDecision = async (proposal, decision) => {
    if (decision === 'accept') {
      await acceptAgentActionProposal(proposal.proposal_id, {
        accepted_by: 'human',
        reason: 'Accepted from campaign workspace UI',
        confidence: 0.6,
        metadata: { ui_surface: 'campaign_workspace' },
      })
      return
    }
    if (decision === 'reject') {
      await rejectAgentActionProposal(proposal.proposal_id, {
        reviewed_by: 'human',
        reason: 'Rejected from campaign workspace UI',
        confidence: 0.7,
        feedback_tags: ['ui-reject'],
        metadata: { ui_surface: 'campaign_workspace' },
      })
      return
    }
    await suppressAgentActionProposal(proposal.proposal_id, {
      reviewed_by: 'human',
      reason: 'Suppressed from campaign workspace UI',
      confidence: 0.8,
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
      setExperienceTargetReview((current) => ({ ...current, error: 'Нужно указать хотя бы один target' }))
      return
    }
    reviewProposal(proposal, 'accept', { targets })
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
    loadWorkspace,
    handleCreateTask,
    handleFollowup,
    beginAcceptProposal,
    reviewProposal,
    submitExperienceTargets,
  }
}
