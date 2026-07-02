import React from 'react'
import {
  Bot,
  CheckCircle2,
  Inbox,
  MessageSquare,
  PlayCircle,
  Sparkles,
  ThumbsDown,
  XCircle,
} from 'lucide-react'
import { AgentBudgetBadge } from './AgentRuntimeControls'
import {
  canAcceptProposal,
  formatKind,
  formatStatus,
  formatTime,
  isExperienceProposal,
  priorityClass,
  proposalKind,
  statusClass,
} from './agentDisplay'

export const Badge = ({ children, className = '' }) => (
  <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}>
    {children}
  </span>
)

export const EmptyState = ({ icon: Icon = Inbox, title, description }) => (
  <div className="rounded-2xl border border-dashed border-gray-300 bg-white/70 p-8 text-center">
    <Icon className="mx-auto text-gray-400" size={32} />
    <h3 className="mt-3 font-semibold text-gray-900">{title}</h3>
    {description && <p className="mt-1 text-sm text-gray-500">{description}</p>}
  </div>
)

export const SectionCard = ({ title, icon: Icon, children, action }) => (
  <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
    <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
      <div className="flex min-w-0 items-center gap-2">
        {Icon && <Icon className="shrink-0 text-primary-500" size={18} />}
        <h2 className="truncate font-semibold text-gray-900">{title}</h2>
      </div>
      {action}
    </div>
    <div className="p-5">{children}</div>
  </section>
)

export const StatTile = ({ title, value, icon: Icon, tone = 'blue' }) => {
  const tones = {
    blue: 'bg-blue-50 text-blue-600',
    violet: 'bg-violet-50 text-violet-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
  }
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{title}</p>
          <p className="mt-2 text-2xl font-bold text-gray-900">{value ?? 0}</p>
        </div>
        <div className={`rounded-xl p-3 ${tones[tone] || tones.blue}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  )
}

export const MessageCard = ({ message }) => {
  const isUser = message.role === 'user'
  const isDecision = message.message_kind === 'decision'
  const iconClass = isUser
    ? 'bg-gray-900 text-white'
    : isDecision
      ? 'bg-emerald-600 text-white'
      : 'bg-primary-600 text-white'

  return (
    <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex gap-3">
        <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${iconClass}`}>
          {isUser ? <MessageSquare size={17} /> : isDecision ? <CheckCircle2 size={17} /> : <Bot size={17} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-gray-900">{isUser ? 'You' : message.agent_key || 'Agent'}</span>
            <Badge className={isDecision ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-gray-200 bg-gray-50 text-gray-600'}>
              {formatKind(message.message_kind)}
            </Badge>
            <span className="text-xs text-gray-400">{formatTime(message.created_at)}</span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-700">{message.body}</p>
          <AgentBudgetBadge metadata={message.metadata} />
          {(message.proposal_refs?.length > 0 || message.action_refs?.length > 0 || message.fact_refs?.length > 0) && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              {message.proposal_refs?.length > 0 && <Badge className="border-violet-200 bg-violet-50 text-violet-700">proposals: {message.proposal_refs.length}</Badge>}
              {message.action_refs?.length > 0 && <Badge className="border-blue-200 bg-blue-50 text-blue-700">actions: {message.action_refs.length}</Badge>}
              {message.fact_refs?.length > 0 && <Badge className="border-amber-200 bg-amber-50 text-amber-700">facts: {message.fact_refs.length}</Badge>}
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

export const ProposalCard = ({ proposal, onAccept, onReject, onSuppress, busy }) => {
  const canAccept = canAcceptProposal(proposal)
  const kind = proposalKind(proposal)
  const experience = isExperienceProposal(proposal)
  const sourceValue = experience ? 'GDS experience' : proposal.agent_key

  return (
    <article className={`rounded-2xl border bg-white p-4 shadow-sm ${experience ? 'border-violet-200' : 'border-gray-200'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-gray-900">{proposal.title}</h3>
            <Badge className={statusClass(proposal.status)}>{formatStatus(proposal.status)}</Badge>
            <Badge className={priorityClass(proposal.priority)}>{proposal.priority || 'medium'}</Badge>
            <Badge className={experience ? 'border-violet-200 bg-violet-50 text-violet-700' : 'border-gray-200 bg-gray-50 text-gray-600'}>{kind}</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-gray-600">{proposal.summary}</p>
          {proposal.rationale && <p className="mt-2 text-xs leading-5 text-gray-500">{proposal.rationale}</p>}
        </div>
        <Sparkles className="shrink-0 text-violet-400" size={18} />
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-gray-500 sm:grid-cols-2">
        <div>{experience ? 'Source' : 'Agent'}: <span className="font-medium text-gray-700">{sourceValue || 'not set'}</span></div>
        <div>Type: <span className="font-medium text-gray-700">{proposal.proposal_type || kind}</span></div>
        <div>Capability: <span className="font-medium text-gray-700">{proposal.capability_id || 'not set'}</span></div>
        <div>Profile: <span className="font-medium text-gray-700">{proposal.profile_id || 'not set'}</span></div>
      </div>
      {proposal.expected_gain && (
        <p className="mt-3 rounded-xl bg-gray-50 px-3 py-2 text-xs text-gray-600">Expected gain: {proposal.expected_gain}</p>
      )}
      {(proposal.status === 'pending' || proposal.status === 'accept_failed') && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onAccept(proposal)}
            disabled={busy || !canAccept}
            title={canAccept ? 'Accept proposal' : 'Missing capability, profile, or target'}
            className="inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            <PlayCircle size={15} /> {canAccept ? (proposal.status === 'accept_failed' ? 'Retry' : 'Accept') : 'Not ready'}
          </button>
          <button
            type="button"
            onClick={() => onReject(proposal)}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <ThumbsDown size={15} /> Reject
          </button>
          <button
            type="button"
            onClick={() => onSuppress(proposal)}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            <XCircle size={15} /> Suppress similar
          </button>
        </div>
      )}
    </article>
  )
}
