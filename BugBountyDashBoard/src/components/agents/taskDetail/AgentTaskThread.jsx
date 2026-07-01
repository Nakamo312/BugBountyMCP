import React from 'react'
import { Bot, Loader, MessageSquare, Send } from 'lucide-react'
import { AgentRuntimeModeControl, isDeepRuntimeMode } from '../AgentRuntimeControls'
import { Badge, EmptyState, MessageCard, SectionCard } from '../AgentCards'

function FollowupComposer({ actionBusy, deepConfirmed, followup, mode, onDeepConfirmedChange, onFollowupChange, onModeChange, onSubmit }) {
  const disabled = actionBusy || !followup.trim() || (isDeepRuntimeMode(mode) && !deepConfirmed)
  return (
    <form onSubmit={onSubmit} className="rounded-2xl border border-gray-200 bg-gray-50 p-3">
      <div className="space-y-3">
        <div className="flex gap-3">
          <textarea
            value={followup}
            onChange={(event) => onFollowupChange(event.target.value)}
            rows={3}
            placeholder="Спросить агента по этой задаче..."
            className="min-h-[72px] flex-1 resize-none rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          />
          <button
            type="submit"
            disabled={disabled}
            className="inline-flex items-center justify-center rounded-xl bg-primary-600 px-4 text-white hover:bg-primary-700 disabled:opacity-50"
            title="Отправить follow-up"
          >
            {actionBusy ? <Loader className="animate-spin" size={18} /> : <Send size={18} />}
          </button>
        </div>
        <AgentRuntimeModeControl
          mode={mode}
          onModeChange={onModeChange}
          deepConfirmed={deepConfirmed}
          onDeepConfirmedChange={onDeepConfirmedChange}
          compact
        />
      </div>
    </form>
  )
}

export function AgentTaskThread({ actionBusy, followupState, messages, onSubmit, targetAgent }) {
  return (
    <SectionCard title="Live thread" icon={Bot} action={<Badge className="border-gray-200 bg-gray-50 text-gray-600">{targetAgent || 'agent'}</Badge>}>
      <div className="space-y-4">
        {messages.length > 0 ? (
          messages.map((message) => <MessageCard key={message.message_id} message={message} />)
        ) : (
          <EmptyState icon={MessageSquare} title="Сообщений пока нет" description="Здесь появятся промты и ответы агента." />
        )}
        <FollowupComposer actionBusy={actionBusy} onSubmit={onSubmit} {...followupState} />
      </div>
    </SectionCard>
  )
}
