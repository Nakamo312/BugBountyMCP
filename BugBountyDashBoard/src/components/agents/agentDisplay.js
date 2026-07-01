export const STATUS_LABELS = {
  pending: 'pending',
  running: 'running',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
  pending_approval: 'pending approval',
  requires_approval: 'requires approval',
  queued: 'queued',
  blocked: 'blocked',
  accepting: 'accepting',
  accepted: 'accepted',
  accept_failed: 'accept failed',
  rejected: 'rejected',
  suppressed: 'suppressed',
}

export const KIND_LABELS = {
  note: 'note',
  finding: 'finding',
  proposal: 'proposal',
  question: 'question',
  decision: 'decision',
  error: 'error',
}

export const priorityClass = (priority) => {
  switch ((priority || '').toLowerCase()) {
    case 'high':
    case 'critical':
      return 'border-red-200 bg-red-50 text-red-700'
    case 'low':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    default:
      return 'border-amber-200 bg-amber-50 text-amber-700'
  }
}

export const statusClass = (status) => {
  switch ((status || '').toLowerCase()) {
    case 'completed':
    case 'accepted':
    case 'allowed':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    case 'running':
    case 'queued':
    case 'accepting':
      return 'border-blue-200 bg-blue-50 text-blue-700'
    case 'pending':
    case 'requires_approval':
    case 'pending_approval':
      return 'border-amber-200 bg-amber-50 text-amber-700'
    case 'accept_failed':
    case 'rejected':
    case 'suppressed':
    case 'blocked':
    case 'failed':
      return 'border-red-200 bg-red-50 text-red-700'
    default:
      return 'border-gray-200 bg-gray-50 text-gray-600'
  }
}

export const formatStatus = (status) => STATUS_LABELS[status] || status || '—'
export const formatKind = (kind) => KIND_LABELS[kind] || kind || 'message'

export const formatTime = (value) => {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: 'short',
    }).format(new Date(value))
  } catch (error) {
    return value
  }
}

export const shortId = (value) => (value ? String(value).slice(0, 8) : '—')

export const proposalKind = (proposal) => proposal?.proposal_kind || proposal?.kind || 'agent'

export const isExperienceProposal = (proposal) => (
  proposalKind(proposal) === 'experience' || proposalKind(proposal) === 'action_experience_proposal'
)

export const proposalTargets = (proposal) => {
  const params = proposal?.action_params || {}
  if (Array.isArray(params.targets)) return params.targets.filter(Boolean)
  if (params.target) return [params.target]
  return []
}

export const parseTargetList = (value) => String(value || '')
  .split(/[\n,]+/)
  .map((item) => item.trim())
  .filter(Boolean)

export const canAcceptProposal = (proposal) => Boolean(
  proposal?.capability_id
  && proposal?.profile_id
  && (isExperienceProposal(proposal) || proposalTargets(proposal).length > 0),
)

export const asExperienceProposalCard = (proposal) => {
  const explanation = proposal?.explanation || {}
  const source = explanation.source || 'gds-experience'
  const score = Number(proposal?.utility_score || 0)
  const component = explanation.component_id ? ` · component ${String(explanation.component_id).slice(0, 8)}` : ''
  return {
    ...proposal,
    proposal_kind: 'experience',
    title: `${proposal.capability_id}/${proposal.profile_id}`,
    summary: `Graph experience proposal from ${source}${component}. Utility ${score.toFixed(2)}, similarity ${Number(proposal.avg_similarity || 0).toFixed(2)}, samples ${proposal.sample_count || 0}.`,
    rationale: explanation.review?.reason || explanation.proposal_review_prior?.summary || explanation.source,
    priority: score >= 3 ? 'high' : score >= 1 ? 'medium' : 'low',
  }
}
