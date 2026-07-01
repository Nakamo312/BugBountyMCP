import React from 'react'
import {
  CheckCircle2,
  Inbox,
  MessageSquare,
  PlayCircle,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { StatTile } from '../AgentCards'

export function AgentTaskStats({ counts }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
      <StatTile title="Сообщения" value={counts?.messages} icon={MessageSquare} tone="blue" />
      <StatTile title="Предложения" value={counts?.proposals} icon={Sparkles} tone="violet" />
      <StatTile title="Ждут решения" value={counts?.pending_proposals} icon={Inbox} tone="amber" />
      <StatTile title="Решения" value={counts?.decisions} icon={CheckCircle2} tone="emerald" />
      <StatTile title="Action’ы" value={counts?.accepted_actions} icon={PlayCircle} tone="blue" />
      <StatTile title="Outcomes" value={counts?.related_outcomes} icon={ShieldCheck} tone="violet" />
    </div>
  )
}
