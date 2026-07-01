import React from 'react'
import { AlertTriangle, Loader } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { AgentRuntimeUsagePanel } from '../components/agents/AgentRuntimeControls'
import { EmptyState } from '../components/agents/AgentCards'
import {
  AgentTaskActivity,
  AgentTaskContextSidebar,
  AgentTaskHeader,
  AgentTaskOutcomes,
  AgentTaskProposals,
  AgentTaskStats,
  AgentTaskThread,
} from '../components/agents/taskDetail'
import { useProgram } from '../context/ProgramContext'
import { useAgentTaskActivity } from '../hooks/useAgentTaskActivity'
import { useAgentTaskDetail } from '../hooks/useAgentTaskDetail'
import { useAgentTaskInteractions } from '../hooks/useAgentTaskInteractions'

const LoadingTask = () => (
  <div className="flex min-h-[420px] items-center justify-center text-gray-500">
    <Loader className="mr-2 animate-spin" size={20} /> Загрузка задачи
  </div>
)

const MissingTask = () => (
  <EmptyState
    icon={AlertTriangle}
    title="Задача не найдена"
    description="Проверь task id или вернись в рабочую комнату кампании."
  />
)

const ErrorBanner = ({ error }) => {
  if (!error) return null
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <AlertTriangle className="mt-0.5 shrink-0" size={18} />
      <span>{String(error)}</span>
    </div>
  )
}

export default function AgentTaskDetailPage() {
  const { taskId } = useParams()
  const { selectedProgram } = useProgram()
  const { detail, error, loading, reloadDetail, setError, sortedMessages } = useAgentTaskDetail(taskId)
  const programId = detail?.task?.program_id || selectedProgram?.id
  const context = detail?.compact_context || {}
  const { activity } = useAgentTaskActivity({ programId, taskId })
  const interactions = useAgentTaskInteractions({ onChanged: reloadDetail, setError, taskId })

  if (loading && !detail) return <LoadingTask />
  if (!detail && !loading) return <MissingTask />

  const task = detail?.task
  const followupState = {
    deepConfirmed: interactions.followupDeepConfirmed,
    followup: interactions.followup,
    mode: interactions.followupRuntimeMode,
    onDeepConfirmedChange: interactions.setFollowupDeepConfirmed,
    onFollowupChange: interactions.setFollowup,
    onModeChange: interactions.setFollowupRuntimeMode,
  }

  return (
    <div className="space-y-6">
      <AgentTaskHeader loading={loading} onRefresh={reloadDetail} task={task} />
      <ErrorBanner error={error} />
      <AgentTaskStats counts={detail?.counts} />
      <AgentRuntimeUsagePanel summary={context.agent_runtime_usage} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <AgentTaskThread
            actionBusy={interactions.actionBusy}
            followupState={followupState}
            messages={sortedMessages}
            onSubmit={interactions.submitFollowup}
            targetAgent={task?.target_agent}
          />
          <AgentTaskProposals
            actionBusy={interactions.actionBusy}
            onReview={interactions.reviewProposal}
            proposals={detail?.proposals || []}
          />
          <AgentTaskOutcomes outcomes={detail?.related_outcomes || []} />
        </div>

        <div className="space-y-6">
          <AgentTaskContextSidebar acceptedActions={detail?.accepted_actions || []} context={context} />
          <AgentTaskActivity activity={activity} />
        </div>
      </div>
    </div>
  )
}
