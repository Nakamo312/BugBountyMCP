import React from 'react'
import { Bot, FileText, GitBranch, MessageSquare, PlayCircle, ShieldCheck, Sparkles, Target, Activity } from 'lucide-react'
import { Badge, EmptyState, SectionCard, StatTile } from '../AgentCards'
import { formatStatus, statusClass } from '../agentDisplay'

const ContextList = ({ title, items, empty }) => (
  <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
    <h3 className="font-semibold text-gray-900">{title}</h3>
    {items?.length > 0 ? (
      <div className="mt-3 space-y-2">
        {items.map((item, index) => (
          <div key={`${item.kind || item.id || index}-${index}`} className="rounded-xl bg-gray-50 px-3 py-2 text-xs text-gray-600">
            <span className="font-medium text-gray-800">{item.kind || item.type || 'ref'}</span>
            {item.id || item.url || item.value ? <span className="ml-2 break-all text-gray-500">{item.id || item.url || item.value}</span> : null}
          </div>
        ))}
      </div>
    ) : (
      <p className="mt-2 text-sm text-gray-500">{empty}</p>
    )}
  </div>
)

const SurfaceSummary = ({ summary }) => {
  const counts = summary?.counts || {}
  const httpSamples = summary?.http_samples || []
  const jsSamples = summary?.javascript_samples || []
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <StatTile title="Hosts" value={counts.hosts} icon={Target} tone="blue" />
        <StatTile title="Endpoints" value={counts.endpoints} icon={GitBranch} tone="violet" />
        <StatTile title="HTTP obs" value={counts.http_observations} icon={Activity} tone="amber" />
        <StatTile title="JS refs" value={counts.javascript_references} icon={FileText} tone="emerald" />
      </div>
      <ContextList title="HTTP samples" items={httpSamples.map((sample) => ({ kind: sample.method || 'HTTP', url: sample.url }))} empty="No HTTP samples yet." />
      <ContextList title="JS samples" items={jsSamples.map((sample) => ({ kind: sample.reference_type || 'JS', url: sample.referenced_url || sample.source_url }))} empty="No JS samples yet." />
    </div>
  )
}

const ContextSnapshot = ({ context }) => (
  <SectionCard title="Compact context" icon={FileText}>
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <StatTile title="User msg" value={context.thread_summary?.user_messages} icon={MessageSquare} tone="blue" />
        <StatTile title="Agent msg" value={context.thread_summary?.agent_messages} icon={Bot} tone="violet" />
        <StatTile title="Pending" value={context.proposal_summary?.pending} icon={Sparkles} tone="amber" />
        <StatTile title="Avg gain" value={Number(context.outcome_summary?.avg_information_gain_score || 0).toFixed(2)} icon={ShieldCheck} tone="emerald" />
      </div>
      {context.last_user_message_excerpt && (
        <div className="rounded-2xl bg-gray-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Latest prompt</p>
          <p className="mt-2 text-sm leading-6 text-gray-700">{context.last_user_message_excerpt}</p>
        </div>
      )}
      {context.last_agent_message_excerpt && (
        <div className="rounded-2xl bg-primary-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-primary-600">Latest agent response</p>
          <p className="mt-2 text-sm leading-6 text-gray-700">{context.last_agent_message_excerpt}</p>
        </div>
      )}
      <ContextList title="Context refs" items={context.context_refs || []} empty="No context refs attached." />
    </div>
  </SectionCard>
)

const AcceptedActions = ({ actions }) => (
  <SectionCard title="Accepted actions" icon={PlayCircle}>
    {actions?.length > 0 ? (
      <div className="space-y-3">
        {actions.map((action) => (
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
      <EmptyState title="No actions yet" description="A proposal must be explicitly accepted before ActionService decides queued, approval, or blocked state." />
    )}
  </SectionCard>
)

const BoundaryNotes = () => (
  <SectionCard title="Boundaries" icon={Target}>
    <div className="space-y-2 text-xs text-gray-600">
      <div className="rounded-xl bg-gray-50 px-3 py-2">Tools run only through ActionService.</div>
      <div className="rounded-xl bg-gray-50 px-3 py-2">This screen does not read raw artifacts or raw response bodies.</div>
      <div className="rounded-xl bg-gray-50 px-3 py-2">This read model does not start GDS or agents.</div>
    </div>
  </SectionCard>
)

export function AgentTaskContextSidebar({ acceptedActions, context }) {
  return (
    <div className="space-y-6">
      <ContextSnapshot context={context} />
      <SectionCard title="Surface snapshot" icon={GitBranch}>
        <SurfaceSummary summary={context.surface_summary || {}} />
      </SectionCard>
      <AcceptedActions actions={acceptedActions} />
      <BoundaryNotes />
    </div>
  )
}
