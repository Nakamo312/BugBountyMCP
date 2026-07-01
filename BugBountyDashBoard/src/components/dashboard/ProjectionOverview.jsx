import React from 'react'
import { Link } from 'react-router-dom'
import { Activity, AlertCircle, Database, GitBranch, Loader, RefreshCw, Terminal } from 'lucide-react'
import { OperatorPlan } from './OperatorPlan'
import { StatusBadge } from './StatusBadge'
import { queueBacklog, queueUnhealthy } from './dashboardUi'

const CommandList = ({ commands }) => (
  <div className="mt-3 space-y-2">
    {commands.map((command) => (
      <code key={command} className="block overflow-x-auto rounded bg-gray-900 px-3 py-2 text-xs text-gray-100">
        {command}
      </code>
    ))}
  </div>
)

const QueueRow = ({ label, queue }) => {
  const healthy = queueBacklog(queue) === 0 && queueUnhealthy(queue) === 0
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
      <div>
        <div className="text-sm font-medium text-gray-900">{label}</div>
        <div className="text-xs text-gray-500">
          pending {queue?.pending || 0} · locked {queue?.locked || 0} · failed {queue?.failed || 0} · dead {queue?.dead || 0}
        </div>
      </div>
      <StatusBadge ok={healthy} label={healthy ? 'clear' : 'attention'} />
    </div>
  )
}

const ProjectionAuditCommands = ({ programId }) => {
  if (!programId) return null
  const commands = [
    `python -m bb_cli --program-id ${programId} projection audit-summary`,
    `python -m bb_cli --program-id ${programId} projection audit --limit 20`,
  ]
  return (
    <div className="mt-5 rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-gray-900">
            <Terminal className="text-gray-500" size={18} />
            Advanced local run-step audit
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            Hidden diagnostic fallback for local JSONL audit files. The primary UI should expose backend projection controls instead of asking the user to run commands.
          </p>
        </div>
        <StatusBadge ok label="CLI-local" />
      </div>
      <CommandList commands={commands} />
      <p className="mt-3 text-xs text-gray-500">Read-only guidance only. Browser UI does not execute commands and does not access local files.</p>
    </div>
  )
}

const FreshnessCard = ({ label, ok, okLabel, badLabel, detail }) => (
  <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
    <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
    <div className="mt-2"><StatusBadge ok={ok} label={ok ? okLabel : badLabel} /></div>
    <div className="mt-3 text-xs text-gray-500">{detail}</div>
  </div>
)

const ProjectionFreshnessCards = ({ overview }) => (
  <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
    <FreshnessCard
      label="Surface analysis"
      ok={overview.surface_analysis_fresh}
      okLabel="fresh"
      badLabel="stale"
      detail={`snapshot ${overview.latest_surface_snapshot?.snapshot_id || 'n/a'}`}
    />
    <FreshnessCard
      label="Search index"
      ok={overview.search_index_fresh}
      okLabel="fresh"
      badLabel="stale"
      detail={`analysis ${overview.latest_surface_analysis?.analysis_run_id || 'n/a'}`}
    />
    <FreshnessCard
      label="UI data"
      ok={overview.ui_data_fresh}
      okLabel="ready"
      badLabel="needs work"
      detail={`pending proposals ${overview.experience_proposals?.pending || 0}`}
    />
  </div>
)

const ProjectionQueues = ({ overview }) => [
  ['Graph projection events', overview.graph_projection_events],
  ['Graph fact batches', overview.graph_fact_batches],
  ['Surface analysis events', overview.surface_analysis_events],
  ['Search projection events', overview.search_projection_events],
].map(([label, queue]) => <QueueRow key={label} label={label} queue={queue} />)

const ProjectionLinks = () => (
  <div className="mt-5 flex flex-wrap gap-2">
    <Link to="/graph/components" className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-3 py-2 text-sm text-white hover:bg-primary-700">
      <GitBranch size={16} />
      Component analysis
    </Link>
    <Link to="/execution" className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
      <Activity size={16} />
      Review execution
    </Link>
  </div>
)

const SuggestedCommands = ({ commands }) => {
  if (!commands.length) return null
  return (
    <details className="mt-5 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-gray-500">Advanced local CLI fallbacks</summary>
      <CommandList commands={commands.slice(0, 5)} />
      <p className="mt-3 text-xs text-gray-500">These are not the primary dashboard workflow. They remain only for local diagnostics when backend projection controls are unavailable.</p>
    </details>
  )
}

const ProjectionEmptyState = ({ error }) => {
  if (error) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-5">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 text-yellow-600" size={20} />
          <div>
            <h3 className="font-semibold text-yellow-900">Projection overview unavailable</h3>
            <p className="mt-1 text-sm text-yellow-700">{error}</p>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow">
      <div className="flex items-start gap-3">
        <Database className="mt-0.5 text-gray-400" size={20} />
        <div>
          <h3 className="font-semibold text-gray-900">No projection state yet</h3>
          <p className="mt-1 text-sm text-gray-600">Build a surface snapshot and let the projection pipeline run before this card can report freshness.</p>
        </div>
      </div>
    </div>
  )
}

export const ProjectionOverview = ({ overview, operatorPlan, loading, error, onRefresh }) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-gray-200 bg-white p-8 shadow">
        <Loader className="animate-spin text-primary-500" size={24} />
      </div>
    )
  }
  if (error || !overview) return <ProjectionEmptyState error={error} />

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold text-gray-900">
            <GitBranch className="text-primary-500" size={22} />
            Projection Pipeline
          </h2>
          <p className="mt-1 text-sm text-gray-600">End-to-end read-only state for Surface Map, component analysis, search projection, and experience proposals.</p>
        </div>
        <button onClick={onRefresh} className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <ProjectionFreshnessCards overview={overview} />
      <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-2"><ProjectionQueues overview={overview} /></div>
      <ProjectionLinks />
      <SuggestedCommands commands={overview.suggested_commands || []} />
      <OperatorPlan plan={operatorPlan} />
      <details className="mt-5">
        <summary className="cursor-pointer text-sm font-medium text-gray-700">Advanced local projection diagnostics</summary>
        <ProjectionAuditCommands programId={overview.program_id} />
      </details>
    </div>
  )
}
