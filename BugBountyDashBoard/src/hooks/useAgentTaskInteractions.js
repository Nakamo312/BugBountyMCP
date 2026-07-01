import { useState } from 'react'
import {
  acceptAgentActionProposal,
  appendAgentTaskMessage,
  rejectAgentActionProposal,
  suppressAgentActionProposal,
} from '../services/api'
import { buildAgentRuntimeMetadata, isDeepRuntimeMode } from '../components/agents/AgentRuntimeControls'

const UI_SURFACE = 'agent_task_detail_page'

const actionError = (err, fallback) => err.response?.data?.detail || err.message || fallback

const proposalReviewPayload = (decision) => {
  if (decision === 'accept') {
    return {
      accepted_by: 'human',
      reason: 'Accepted from agent task detail UI',
      metadata: { ui_surface: UI_SURFACE },
    }
  }
  return {
    reviewed_by: 'human',
    reason: `${decision === 'reject' ? 'Rejected' : 'Suppressed'} from agent task detail UI`,
    feedback_tags: [`ui-${decision}`],
    metadata: { ui_surface: UI_SURFACE },
  }
}

export function useAgentTaskInteractions({ onChanged, setError, taskId }) {
  const [actionBusy, setActionBusy] = useState(false)
  const [followup, setFollowup] = useState('')
  const [followupRuntimeMode, setFollowupRuntimeMode] = useState('none')
  const [followupDeepConfirmed, setFollowupDeepConfirmed] = useState(false)

  const submitFollowup = async (event) => {
    event.preventDefault()
    if (!taskId || !followup.trim()) return
    if (isDeepRuntimeMode(followupRuntimeMode) && !followupDeepConfirmed) return
    setActionBusy(true)
    setError(null)
    try {
      await appendAgentTaskMessage(taskId, {
        body: followup,
        created_by: 'human',
        source: 'ui',
        metadata: buildAgentRuntimeMetadata({
          mode: followupRuntimeMode,
          deepConfirmed: followupDeepConfirmed,
          uiSurface: UI_SURFACE,
        }),
      })
      setFollowup('')
      setFollowupDeepConfirmed(false)
      await onChanged()
    } catch (err) {
      setError(actionError(err, 'Не удалось отправить сообщение'))
    } finally {
      setActionBusy(false)
    }
  }

  const reviewProposal = async (proposal, decision) => {
    const reviewAction = {
      accept: acceptAgentActionProposal,
      reject: rejectAgentActionProposal,
      suppress: suppressAgentActionProposal,
    }[decision]
    if (!reviewAction) return
    setActionBusy(true)
    setError(null)
    try {
      await reviewAction(proposal.proposal_id, proposalReviewPayload(decision))
      await onChanged()
    } catch (err) {
      setError(actionError(err, 'Не удалось применить решение'))
    } finally {
      setActionBusy(false)
    }
  }

  return {
    actionBusy,
    followup,
    followupDeepConfirmed,
    followupRuntimeMode,
    reviewProposal,
    setFollowup,
    setFollowupDeepConfirmed,
    setFollowupRuntimeMode,
    submitFollowup,
  }
}
