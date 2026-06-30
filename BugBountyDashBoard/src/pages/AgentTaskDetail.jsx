import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  GitBranch,
  Inbox,
  Loader,
  MessageSquare,
  PlayCircle,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
} from 'lucide-react'
import {
  acceptAgentActionProposal,
  appendAgentTaskMessage,
  getAgentActivity,
  getAgentTaskDetail,
  rejectAgentActionProposal,
  suppressAgentActionProposal,
} from '../services/api'
import { useProgram } from '../context/ProgramContext'
import {
  AgentRuntimeModeControl,
  AgentRuntimeUsagePanel,
  buildAgentRuntimeMetadata,
  isDeepRuntimeMode,
} from '../components/agents/AgentRuntimeControls'
import {
  Badge,
  EmptyState,
  MessageCard,
  ProposalCard,
  SectionCard,
  StatTile,
} from '../components/agents/AgentCards'
import { formatStatus, formatTime, shortId, statusClass } from '../components/agents/agentDisplay'

const ActivityRow = ({ event }) => (
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
      <ContextList title="HTTP samples" items={httpSamples.map((sample) => ({ kind: sample.method || 'HTTP', url: sample.url }))} empty="HTTP samples пока нет." />
      <ContextList title="JS samples" items={jsSamples.map((sample) => ({ kind: sample.reference_type || 'JS', url: sample.referenced_url || sample.source_url }))} empty="JS samples пока нет." />
    </div>
  )
}

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

export default function AgentTaskDetailPage() {
  const { taskId } = useParams()
  const { selectedProgram } = useProgram()
  const [detail, setDetail] = useState(null)
  const [activity, setActivity] = useState([])
  const [activityCursor, setActivityCursor] = useState(null)
  const [followup, setFollowup] = useState('')
  const [followupRuntimeMode, setFollowupRuntimeMode] = useState('none')
  const [followupDeepConfirmed, setFollowupDeepConfirmed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [error, setError] = useState(null)

  const programId = detail?.task?.program_id || selectedProgram?.id
  const context = detail?.compact_context || {}
  const sortedMessages = useMemo(
    () => [...(detail?.messages || [])].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0)),
    [detail?.messages],
  )

  const loadDetail = useCallback(async () => {
    if (!taskId) return
    setLoading(true)
    setError(null)
    try {
      const response = await getAgentTaskDetail(taskId, {
        message_limit: 200,
        proposal_limit: 100,
        outcome_limit: 30,
      })
      setDetail(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Не удалось загрузить задачу')
    } finally {
      setLoading(false)
    }
  }, [taskId])

  const loadActivity = useCallback(async () => {
    if (!programId || !taskId) return
    try {
      const response = await getAgentActivity({
        program_id: programId,
        task_id: taskId,
        after: activityCursor || undefined,
        limit: 50,
      })
      const events = response.data?.events || []
      if (events.length > 0) {
        setActivity((current) => [...events, ...current].slice(0, 80))
        setActivityCursor(response.data.next_after || activityCursor)
        await loadDetail()
      }
    } catch (err) {
      console.warn('Agent task activity polling failed:', err)
    }
  }, [activityCursor, loadDetail, programId, taskId])

  useEffect(() => {
    setActivity([])
    setActivityCursor(null)
    loadDetail()
  }, [loadDetail])

  useEffect(() => {
    const interval = window.setInterval(() => {
      loadActivity()
    }, 8000)
    return () => window.clearInterval(interval)
  }, [loadActivity])

  const handleFollowup = async (event) => {
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
          uiSurface: 'agent_task_detail_page',
        }),
      })
      setFollowup('')
      setFollowupDeepConfirmed(false)
      await loadDetail()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Не удалось отправить сообщение')
    } finally {
      setActionBusy(false)
    }
  }

  const reviewProposal = async (proposal, decision) => {
    setActionBusy(true)
    setError(null)
    try {
      if (decision === 'accept') {
        await acceptAgentActionProposal(proposal.proposal_id, {
          accepted_by: 'human',
          reason: 'Accepted from agent task detail UI',
          metadata: { ui_surface: 'agent_task_detail_page' },
        })
      } else if (decision === 'reject') {
        await rejectAgentActionProposal(proposal.proposal_id, {
          reviewed_by: 'human',
          reason: 'Rejected from agent task detail UI',
          feedback_tags: ['ui-reject'],
          metadata: { ui_surface: 'agent_task_detail_page' },
        })
      } else {
        await suppressAgentActionProposal(proposal.proposal_id, {
          reviewed_by: 'human',
          reason: 'Suppressed from agent task detail UI',
          feedback_tags: ['ui-suppress'],
          metadata: { ui_surface: 'agent_task_detail_page' },
        })
      }
      await loadDetail()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Не удалось применить решение')
    } finally {
      setActionBusy(false)
    }
  }

  if (loading && !detail) {
    return (
      <div className="flex min-h-[420px] items-center justify-center text-gray-500">
        <Loader className="mr-2 animate-spin" size={20} /> Загрузка задачи
      </div>
    )
  }

  if (!detail && !loading) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Задача не найдена"
        description="Проверь task id или вернись в рабочую комнату кампании."
      />
    )
  }

  const task = detail?.task

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <Link to="/workspace" className="inline-flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-700">
            <ArrowLeft size={16} /> К рабочей комнате
          </Link>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold text-gray-900">{task?.title || 'Задача агента'}</h1>
            <Badge className={statusClass(task?.status)}>{formatStatus(task?.status)}</Badge>
            <Badge className="border-gray-200 bg-gray-50 text-gray-600">#{shortId(task?.task_id)}</Badge>
          </div>
          <p className="mt-2 max-w-4xl text-gray-600">
            Экран задачи: live thread, предложения агента, принятые action’ы, related outcomes и компактный context. Без запуска GDS/tools из UI.
          </p>
        </div>
        <button
          type="button"
          onClick={() => loadDetail()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
        >
          {loading ? <Loader className="animate-spin" size={16} /> : <Activity size={16} />} Обновить
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <span>{String(error)}</span>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <StatTile title="Сообщения" value={detail?.counts?.messages} icon={MessageSquare} tone="blue" />
        <StatTile title="Предложения" value={detail?.counts?.proposals} icon={Sparkles} tone="violet" />
        <StatTile title="Ждут решения" value={detail?.counts?.pending_proposals} icon={Inbox} tone="amber" />
        <StatTile title="Решения" value={detail?.counts?.decisions} icon={CheckCircle2} tone="emerald" />
        <StatTile title="Action’ы" value={detail?.counts?.accepted_actions} icon={PlayCircle} tone="blue" />
        <StatTile title="Outcomes" value={detail?.counts?.related_outcomes} icon={ShieldCheck} tone="violet" />
      </div>

      <AgentRuntimeUsagePanel summary={context.agent_runtime_usage} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <SectionCard title="Live thread" icon={Bot} action={<Badge className="border-gray-200 bg-gray-50 text-gray-600">{task?.target_agent || 'agent'}</Badge>}>
            <div className="space-y-4">
              {sortedMessages.length > 0 ? (
                sortedMessages.map((message) => <MessageCard key={message.message_id} message={message} />)
              ) : (
                <EmptyState icon={MessageSquare} title="Сообщений пока нет" description="Здесь появятся промты и ответы агента." />
              )}
              <form onSubmit={handleFollowup} className="rounded-2xl border border-gray-200 bg-gray-50 p-3">
                <div className="space-y-3">
                  <div className="flex gap-3">
                    <textarea
                      value={followup}
                      onChange={(event) => setFollowup(event.target.value)}
                      rows={3}
                      placeholder="Спросить агента по этой задаче..."
                      className="min-h-[72px] flex-1 resize-none rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                    />
                    <button
                      type="submit"
                      disabled={actionBusy || !followup.trim() || (isDeepRuntimeMode(followupRuntimeMode) && !followupDeepConfirmed)}
                      className="inline-flex items-center justify-center rounded-xl bg-primary-600 px-4 text-white hover:bg-primary-700 disabled:opacity-50"
                      title="Отправить follow-up"
                    >
                      {actionBusy ? <Loader className="animate-spin" size={18} /> : <Send size={18} />}
                    </button>
                  </div>
                  <AgentRuntimeModeControl
                    mode={followupRuntimeMode}
                    onModeChange={setFollowupRuntimeMode}
                    deepConfirmed={followupDeepConfirmed}
                    onDeepConfirmedChange={setFollowupDeepConfirmed}
                    compact
                  />
                </div>
              </form>
            </div>
          </SectionCard>

          <SectionCard title="Предложения агента" icon={Sparkles}>
            {detail?.proposals?.length > 0 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                {detail.proposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.proposal_id}
                    proposal={proposal}
                    busy={actionBusy}
                    onAccept={(item) => reviewProposal(item, 'accept')}
                    onReject={(item) => reviewProposal(item, 'reject')}
                    onSuppress={(item) => reviewProposal(item, 'suppress')}
                  />
                ))}
              </div>
            ) : (
              <EmptyState title="Предложений пока нет" description="Агент может создать proposal после обработки контекста задачи." />
            )}
          </SectionCard>

          <SectionCard title="Связанные outcomes" icon={ShieldCheck}>
            {detail?.related_outcomes?.length > 0 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                {detail.related_outcomes.map((outcome) => <OutcomeCard key={outcome.outcome_id} outcome={outcome} />)}
              </div>
            ) : (
              <EmptyState title="Outcome context пока нет" description="Когда принятые action’ы завершатся, здесь появится память исходов." />
            )}
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard title="Компактный контекст" icon={FileText}>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <StatTile title="User msg" value={context.thread_summary?.user_messages} icon={MessageSquare} tone="blue" />
                <StatTile title="Agent msg" value={context.thread_summary?.agent_messages} icon={Bot} tone="violet" />
                <StatTile title="Pending" value={context.proposal_summary?.pending} icon={Sparkles} tone="amber" />
                <StatTile title="Avg gain" value={Number(context.outcome_summary?.avg_information_gain_score || 0).toFixed(2)} icon={ShieldCheck} tone="emerald" />
              </div>
              {context.last_user_message_excerpt && (
                <div className="rounded-2xl bg-gray-50 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Последний промт</p>
                  <p className="mt-2 text-sm leading-6 text-gray-700">{context.last_user_message_excerpt}</p>
                </div>
              )}
              {context.last_agent_message_excerpt && (
                <div className="rounded-2xl bg-primary-50 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-primary-600">Последний ответ агента</p>
                  <p className="mt-2 text-sm leading-6 text-gray-700">{context.last_agent_message_excerpt}</p>
                </div>
              )}
              <ContextList title="Context refs" items={context.context_refs || []} empty="Контекстные refs не прикреплены." />
            </div>
          </SectionCard>

          <SectionCard title="Surface snapshot" icon={GitBranch}>
            <SurfaceSummary summary={context.surface_summary || {}} />
          </SectionCard>

          <SectionCard title="Принятые action’ы" icon={PlayCircle}>
            {detail?.accepted_actions?.length > 0 ? (
              <div className="space-y-3">
                {detail.accepted_actions.map((action) => (
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
              <EmptyState title="Action’ов пока нет" description="Proposal должен быть явно принят, потом ActionService решит queued/approval/blocked." />
            )}
          </SectionCard>

          <SectionCard title="Activity" icon={Clock3}>
            {activity.length === 0 ? (
              <EmptyState title="Новых событий нет" description="Лёгкая activity stream обновит экран без полного refresh." />
            ) : (
              <div className="max-h-[360px] overflow-y-auto pr-1">
                {activity.map((event) => <ActivityRow key={event.event_id} event={event} />)}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Границы" icon={Target}>
            <div className="space-y-2 text-xs text-gray-600">
              <div className="rounded-xl bg-gray-50 px-3 py-2">Tools запускаются только через ActionService.</div>
              <div className="rounded-xl bg-gray-50 px-3 py-2">Raw artifacts и raw response bodies не читаются этим экраном.</div>
              <div className="rounded-xl bg-gray-50 px-3 py-2">GDS/агенты не запускаются из detail read-model.</div>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
