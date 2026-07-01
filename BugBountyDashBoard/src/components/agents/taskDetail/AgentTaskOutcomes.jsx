import React from 'react'
import { ShieldCheck } from 'lucide-react'
import { Badge, EmptyState, SectionCard } from '../AgentCards'
import { formatStatus, shortId, statusClass } from '../agentDisplay'

const OutcomeCard = ({ outcome }) => (
  <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h3 className="font-semibold text-gray-900">{outcome.capability_id}</h3>
        <p className="text-xs text-gray-500">{outcome.profile_id} · run #{shortId(outcome.run_id)}</p>
      </div>
      <Badge className={statusClass(outcome.status)}>{formatStatus(outcome.status)}</Badge>
    </div>
    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-500">
      <div>Gain: <span className="font-medium text-gray-800">{Number(outcome.information_gain_score || 0).toFixed(2)}</span></div>
      <div>Endpoints: <span className="font-medium text-gray-800">{outcome.counts?.endpoints || 0}</span></div>
      <div>HTTP: <span className="font-medium text-gray-800">{outcome.counts?.http_observations || 0}</span></div>
      <div>JS refs: <span className="font-medium text-gray-800">{outcome.counts?.javascript_references || 0}</span></div>
    </div>
    {(outcome.human_feedback?.manual_interest || outcome.human_feedback?.manual_stop || outcome.human_feedback?.continued_by_followup) && (
      <div className="mt-3 flex flex-wrap gap-2">
        {outcome.human_feedback.manual_interest && <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">interest</Badge>}
        {outcome.human_feedback.continued_by_followup && <Badge className="border-blue-200 bg-blue-50 text-blue-700">continued</Badge>}
        {outcome.human_feedback.manual_stop && <Badge className="border-red-200 bg-red-50 text-red-700">stopped</Badge>}
      </div>
    )}
  </article>
)

export function AgentTaskOutcomes({ outcomes }) {
  return (
    <SectionCard title="Related outcomes" icon={ShieldCheck}>
      {outcomes?.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {outcomes.map((outcome) => <OutcomeCard key={outcome.outcome_id} outcome={outcome} />)}
        </div>
      ) : (
        <EmptyState title="No outcome context yet" description="Outcome memory appears here after accepted actions finish." />
      )}
    </SectionCard>
  )
}
