import React from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  GitBranch,
  Inbox,
  Loader,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
} from 'lucide-react'
import {
  AgentRuntimeModeControl,
  AgentRuntimeUsagePanel,
  isDeepRuntimeMode,
} from './AgentRuntimeControls'
import {
  Badge,
  EmptyState,
  MessageCard,
  ProposalCard,
  SectionCard,
  StatTile,
} from './AgentCards'
import { ExperienceTargetForm } from './ExperienceTargetForm'
import { AGENT_OPTIONS } from './agentWorkspaceOptions'
import {
  formatStatus,
  formatTime,
  shortId,
  statusClass,
} from './agentDisplay'

export function AgentWorkspaceView({ state }) {
  if (!state.selectedProgram) {
    return (
      <EmptyState
        icon={Target}
        title="Select a program"
        description="Execution is scoped to the selected bug bounty program."
      />
    )
  }

  return (
    <div className="space-y-6">
      <WorkspaceHeader state={state} />
      <WorkspaceError error={state.error} />
      <WorkspaceStats workspace={state.workspace} />
      <AgentRuntimeUsagePanel summary={state.workspace?.agent_runtime_usage} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <NewAgentTaskPanel state={state} />
          <TaskListPanel state={state} />
        </div>
        <TaskThreadPanel state={state} />
        <WorkspaceSidebar state={state} />
      </div>
    </div>
  )
}


function WorkspaceHeader({ state }) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Execution</h1>
        <p className="mt-2 text-gray-600">{state.selectedProgram.name}</p>
      </div>
      <button
        type="button"
        onClick={() => state.loadWorkspace()}
        disabled={state.loading}
        className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
      >
        <RefreshCw className={state.loading ? 'animate-spin' : ''} size={16} /> Refresh
      </button>
    </div>
  )
}

function WorkspaceError({ error }) {
  if (!error) return null
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <AlertTriangle className="mt-0.5 shrink-0" size={18} />
      <span>{String(error)}</span>
    </div>
  )
}

function WorkspaceStats({ workspace }) {
  const pendingCount = (workspace?.counts?.pending_agent_proposals || 0) + (workspace?.counts?.pending_experience_proposals || 0)
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <StatTile title="Agent tasks" value={workspace?.counts?.tasks} icon={Inbox} tone="blue" />
      <StatTile title="Messages" value={workspace?.counts?.visible_messages} icon={MessageSquare} tone="violet" />
      <StatTile title="Pending review" value={pendingCount} icon={Sparkles} tone="amber" />
      <StatTile title="Action queue" value={workspace?.counts?.action_queue} icon={PlayCircle} tone="emerald" />
    </div>
  )
}

function NewAgentTaskPanel({ state }) {
  return (
    <SectionCard title="New agent task" icon={Send}>
      <form onSubmit={state.handleCreateTask} className="space-y-3">
        <select
          value={state.targetAgent}
          onChange={(event) => state.setTargetAgent(event.target.value)}
          className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        >
          {AGENT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <textarea
          value={state.prompt}
          onChange={(event) => state.setPrompt(event.target.value)}
          rows={5}
          placeholder="Example: inspect newly discovered JavaScript paths and identify the next endpoints to review."
          className="w-full resize-none rounded-xl border border-gray-300 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
        <AgentRuntimeModeControl
          mode={state.runtimeMode}
          onModeChange={state.setRuntimeMode}
          deepConfirmed={state.deepConfirmed}
          onDeepConfirmedChange={state.setDeepConfirmed}
        />
        <button
          type="submit"
          disabled={state.actionBusy || !state.prompt.trim() || (isDeepRuntimeMode(state.runtimeMode) && !state.deepConfirmed)}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
        >
          {state.actionBusy ? <Loader className="animate-spin" size={16} /> : <Send size={16} />}
          Create task
        </button>
      </form>
    </SectionCard>
  )
}

function TaskListPanel({ state }) {
  return (
    <SectionCard title="Agent tasks" icon={GitBranch}>
      {state.loading && !state.workspace ? (
        <div className="flex items-center justify-center py-8 text-gray-500">
          <Loader className="mr-2 animate-spin" size={18} /> Loading
        </div>
      ) : state.tasks.length === 0 ? (
        <EmptyState title="No agent tasks yet" description="Create an agent task and its thread will appear here." />
      ) : (
        <div className="space-y-3">
          {state.tasks.map((card) => (
            <TaskListItem
              key={card.task.task_id}
              card={card}
              active={state.selectedTaskId === card.task.task_id}
              onSelect={state.setSelectedTaskId}
            />
          ))}
        </div>
      )}
    </SectionCard>
  )
}

function TaskListItem({ card, active, onSelect }) {
  const latest = [...(card.messages || [])].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0]
  return (
    <button
      type="button"
      onClick={() => onSelect(card.task.task_id)}
      className={`w-full rounded-2xl border p-4 text-left transition ${
        active ? 'border-primary-300 bg-primary-50 shadow-sm' : 'border-gray-200 bg-white hover:border-primary-200 hover:bg-primary-50/40'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-gray-900">{card.task.title}</h3>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-gray-500">{latest?.body || card.task.prompt_excerpt}</p>
        </div>
        <Badge className={statusClass(card.task.status)}>{formatStatus(card.task.status)}</Badge>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
        <span>{card.task.target_agent}</span>
        <span>{card.proposals?.length || 0} proposals</span>
      </div>
    </button>
  )
}

function TaskThreadPanel({ state }) {
  const title = state.selectedTaskCard?.task?.title || state.taskDetail?.task?.title || 'Agent thread'
  return (
    <div className="space-y-6">
      <SectionCard title={title} icon={Bot} action={taskThreadAction(state.selectedTaskId)}>
        {state.selectedTaskId ? <TaskThread state={state} /> : (
          <EmptyState icon={Bot} title="Select a task" description="The selected task thread appears here." />
        )}
      </SectionCard>
    </div>
  )
}

function taskThreadAction(selectedTaskId) {
  if (!selectedTaskId) return null
  return (
    <div className="flex items-center gap-2">
      <Badge className="border-gray-200 bg-gray-50 text-gray-600">#{shortId(selectedTaskId)}</Badge>
      <Link
        to={`/execution/tasks/${selectedTaskId}`}
        className="inline-flex items-center rounded-lg border border-primary-200 px-3 py-1 text-xs font-medium text-primary-700 hover:bg-primary-50"
      >
        Open detail
      </Link>
    </div>
  )
}

function TaskThread({ state }) {
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {state.messages.length > 0 ? (
          state.messages.map((message) => <MessageCard key={message.message_id} message={message} />)
        ) : (
          <EmptyState icon={MessageSquare} title="No messages" description="Waiting for worker output." />
        )}
      </div>
      <form onSubmit={state.handleFollowup} className="rounded-2xl border border-gray-200 bg-gray-50 p-3">
        <div className="space-y-3">
          <div className="flex gap-3">
            <textarea
              value={state.followup}
              onChange={(event) => state.setFollowup(event.target.value)}
              rows={2}
              placeholder="Ask a follow-up about the selected task..."
              className="min-h-[52px] flex-1 resize-none rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
            />
            <button
              type="submit"
              disabled={state.actionBusy || !state.followup.trim() || (isDeepRuntimeMode(state.followupRuntimeMode) && !state.followupDeepConfirmed)}
              className="inline-flex items-center justify-center rounded-xl bg-primary-600 px-4 text-white hover:bg-primary-700 disabled:opacity-50"
              title="Send follow-up"
            >
              <Send size={18} />
            </button>
          </div>
          <AgentRuntimeModeControl
            mode={state.followupRuntimeMode}
            onModeChange={state.setFollowupRuntimeMode}
            deepConfirmed={state.followupDeepConfirmed}
            onDeepConfirmedChange={state.setFollowupDeepConfirmed}
            compact
          />
        </div>
      </form>
    </div>
  )
}

function WorkspaceSidebar({ state }) {
  return (
    <div className="space-y-6">
      <ProposalsPanel state={state} />
      <ActionQueuePanel workspace={state.workspace} />
      <ActivityPanel activity={state.activity} />
    </div>
  )
}

function ProposalsPanel({ state }) {
  return (
    <SectionCard title="Proposals" icon={Sparkles}>
      {state.visibleProposals.length === 0 ? (
        <EmptyState title="No proposals" description="" />
      ) : (
        <div className="space-y-3">
          {state.visibleProposals.map((proposal) => (
            <React.Fragment key={proposal.proposal_id}>
              <ProposalCard
                proposal={proposal}
                busy={state.actionBusy}
                onAccept={state.beginAcceptProposal}
                onReject={(item) => state.reviewProposal(item, 'reject')}
                onSuppress={(item) => state.reviewProposal(item, 'suppress')}
              />
              {state.experienceTargetReview.proposalId === proposal.proposal_id && (
                <ExperienceTargetForm
                  proposal={proposal}
                  value={state.experienceTargetReview.value}
                  error={state.experienceTargetReview.error}
                  busy={state.actionBusy}
                  onChange={(value) => state.setExperienceTargetReview((current) => ({ ...current, value, error: null }))}
                  onSubmit={(event) => state.submitExperienceTargets(event, proposal)}
                  onCancel={() => state.setExperienceTargetReview({ proposalId: null, value: '', error: null })}
                />
              )}
            </React.Fragment>
          ))}
        </div>
      )}
    </SectionCard>
  )
}

function ActionQueuePanel({ workspace }) {
  return (
    <SectionCard title="Action queue" icon={ShieldCheck}>
      {workspace?.action_queue?.length > 0 ? (
        <div className="space-y-3">
          {workspace.action_queue.slice(0, 8).map((action) => (
            <div key={action.action_id} className="rounded-2xl border border-gray-200 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-gray-900">{action.capability_id}</p>
                  <p className="text-xs text-gray-500">{action.profile_id} · {action.requested_by}</p>
                </div>
                <Badge className={statusClass(action.status)}>{formatStatus(action.status)}</Badge>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="Action queue empty" description="" />
      )}
    </SectionCard>
  )
}

function ActivityPanel({ activity }) {
  return (
    <SectionCard title="Activity" icon={Clock3}>
      {activity.length === 0 ? (
        <EmptyState title="No events" description="" />
      ) : (
        <div className="max-h-[420px] overflow-y-auto pr-1">
          {activity.map((event) => <ActivityRow key={event.event_id} event={event} />)}
        </div>
      )}
    </SectionCard>
  )
}

function ActivityRow({ event }) {
  return (
    <div className="flex gap-3 border-b border-gray-100 py-3 last:border-b-0">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white">
        {event.event_type === 'proposal_decision' ? <CheckCircle2 size={15} /> : event.event_type === 'agent_proposal' ? <Sparkles size={15} /> : <Activity size={15} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium text-gray-900">{event.title}</p>
          <span className="shrink-0 text-xs text-gray-400">{formatTime(event.occurred_at)}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-xs leading-5 text-gray-500">{event.summary}</p>
      </div>
    </div>
  )
}
