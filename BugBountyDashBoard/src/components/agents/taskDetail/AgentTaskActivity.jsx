import React from 'react'
import { Activity, CheckCircle2, Clock3, Sparkles } from 'lucide-react'
import { EmptyState, SectionCard } from '../AgentCards'
import { formatTime } from '../agentDisplay'

const activityIcon = (eventType) => {
  if (eventType === 'proposal_decision') return <CheckCircle2 size={15} />
  if (eventType === 'agent_proposal') return <Sparkles size={15} />
  return <Activity size={15} />
}

const ActivityRow = ({ event }) => (
  <div className="flex gap-3 border-b border-gray-100 py-3 last:border-b-0">
    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white">
      {activityIcon(event.event_type)}
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

export function AgentTaskActivity({ activity }) {
  return (
    <SectionCard title="Activity" icon={Clock3}>
      {activity.length === 0 ? (
        <EmptyState title="Новых событий нет" description="Лёгкая activity stream обновит экран без полного refresh." />
      ) : (
        <div className="max-h-[360px] overflow-y-auto pr-1">
          {activity.map((event) => <ActivityRow key={event.event_id} event={event} />)}
        </div>
      )}
    </SectionCard>
  )
}
