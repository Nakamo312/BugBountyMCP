import React from 'react'

export const AGENT_RUNTIME_MODES = [
  {
    value: 'none',
    label: 'Manual',
    shortLabel: 'none',
    description: 'No LLM call. Use this for manual execution notes, deterministic task shells, and operator-controlled follow-up.',
  },
  {
    value: 'cheap',
    label: 'Cheap',
    shortLabel: 'cheap',
    description: 'Short model response over compact context.',
  },
  {
    value: 'normal',
    label: 'Normal',
    shortLabel: 'normal',
    description: 'Bounded model response with more context.',
  },
  {
    value: 'deep',
    label: 'Deep',
    shortLabel: 'deep',
    description: 'Expensive mode. Requires explicit confirmation and can still be downgraded by backend policy.',
  },
]

export const runtimeModeOption = (mode) =>
  AGENT_RUNTIME_MODES.find((option) => option.value === mode) || AGENT_RUNTIME_MODES[0]

export const isDeepRuntimeMode = (mode) => mode === 'deep'

export const buildAgentRuntimeMetadata = ({ mode, deepConfirmed = false, uiSurface, extra = {} }) => ({
  ...extra,
  ui_surface: uiSurface,
  tool_execution: 'forbidden_from_prompt',
  agent_runtime_mode: mode,
  budget_mode: mode,
  model_mode: mode,
  deep_mode_confirmed: isDeepRuntimeMode(mode) ? Boolean(deepConfirmed) : false,
})

const modeButtonClass = (active, value) => {
  const activeClasses = {
    none: 'border-gray-900 bg-gray-900 text-white',
    cheap: 'border-emerald-500 bg-emerald-50 text-emerald-700',
    normal: 'border-primary-500 bg-primary-50 text-primary-700',
    deep: 'border-red-500 bg-red-50 text-red-700',
  }
  return active
    ? activeClasses[value] || activeClasses.none
    : 'border-gray-200 bg-white text-gray-600 hover:border-primary-200 hover:bg-primary-50/50'
}

export function AgentRuntimeModeControl({
  mode,
  onModeChange,
  deepConfirmed,
  onDeepConfirmedChange,
  compact = false,
}) {
  const selected = runtimeModeOption(mode)
  const setMode = (nextMode) => {
    onModeChange(nextMode)
    if (nextMode !== 'deep') onDeepConfirmedChange(false)
  }

  return (
    <div className="rounded-2xl border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Runtime mode</p>
          {!compact && <p className="mt-1 text-xs leading-5 text-gray-500">{selected.description}</p>}
        </div>
        <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-xs font-medium text-gray-600">
          {selected.shortLabel}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {AGENT_RUNTIME_MODES.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setMode(option.value)}
            className={`rounded-xl border px-3 py-2 text-xs font-medium transition ${modeButtonClass(mode === option.value, option.value)}`}
            title={option.description}
          >
            {option.label}
          </button>
        ))}
      </div>
      {mode === 'deep' && (
        <label className="mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-white px-3 py-2 text-xs leading-5 text-red-700">
          <input
            type="checkbox"
            checked={deepConfirmed}
            onChange={(event) => onDeepConfirmedChange(event.target.checked)}
            className="mt-0.5 rounded border-red-300 text-red-600 focus:ring-red-200"
          />
          <span>
            I confirm deep mode. Backend policy can still downgrade this request to normal.
          </span>
        </label>
      )}
    </div>
  )
}

const badgeClass = (mode) => {
  switch (mode) {
    case 'cheap':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    case 'normal':
      return 'border-primary-200 bg-primary-50 text-primary-700'
    case 'deep':
      return 'border-red-200 bg-red-50 text-red-700'
    default:
      return 'border-gray-200 bg-gray-50 text-gray-600'
  }
}

const deepApprovalCopy = {
  deep_mode_disabled: {
    label: 'deep disabled by policy',
    description: 'Backend policy does not allow deep mode globally.',
    className: 'border-red-200 bg-red-50 text-red-700',
  },
  deep_mode_requires_explicit_confirmation: {
    label: 'deep not confirmed',
    description: 'Deep mode requires explicit confirmation.',
    className: 'border-amber-200 bg-amber-50 text-amber-700',
  },
  deep_mode_actor_not_allowed: {
    label: 'actor not allowed',
    description: 'The current actor is not allowed to use deep mode.',
    className: 'border-red-200 bg-red-50 text-red-700',
  },
  deep_mode_approved: {
    label: 'deep approved',
    description: 'Backend policy allowed deep mode for this run.',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  },
}

const budgetReasonCopy = {
  model_usage_disabled: 'model disabled',
  selected: 'selected',
  selected_with_truncation: 'context truncated',
  deep_mode_disabled: 'deep disabled by policy',
  deep_mode_disabled_with_truncation: 'deep disabled, context truncated',
  deep_mode_requires_explicit_confirmation: 'deep not confirmed',
  deep_mode_requires_explicit_confirmation_with_truncation: 'deep not confirmed, context truncated',
  deep_mode_actor_not_allowed: 'actor not allowed',
  deep_mode_actor_not_allowed_with_truncation: 'actor not allowed, context truncated',
  deep_mode_approved: 'deep approved',
  deep_mode_approved_with_truncation: 'deep approved, context truncated',
}

const formatBudgetReason = (reason) => budgetReasonCopy[reason] || reason

const formatDeepApprovalTitle = (deepApproval) => {
  if (!deepApproval) return undefined
  const parts = []
  if (deepApproval.actor) parts.push(`actor: ${deepApproval.actor}`)
  if (deepApproval.confirmation_required) {
    parts.push(`confirmation: ${deepApproval.confirmation_provided ? 'yes' : 'no'}`)
  }
  if (typeof deepApproval.globally_allowed === 'boolean') {
    parts.push(`globally: ${deepApproval.globally_allowed ? 'allowed' : 'disabled'}`)
  }
  if (Array.isArray(deepApproval.allowed_actors) && deepApproval.allowed_actors.length > 0) {
    parts.push(`allowed actors: ${deepApproval.allowed_actors.join(', ')}`)
  }
  return parts.join(' · ') || undefined
}

export function AgentBudgetBadge({ metadata }) {
  const budget = metadata?.budget
  const selectedMode = budget?.selected_mode || metadata?.agent_runtime_mode || metadata?.budget_mode || metadata?.model_mode
  if (!selectedMode) return null
  const requestedMode = budget?.requested_mode
  const llmAllowed = budget?.llm_allowed
  const reason = budget?.reason_code
  const deepApproval = budget?.deep_approval
  const deepCopy = deepApproval ? deepApprovalCopy[deepApproval.reason_code] : null
  const downgraded = requestedMode && requestedMode !== selectedMode

  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${badgeClass(selectedMode)}`}>
        mode: {selectedMode}
      </span>
      {typeof llmAllowed === 'boolean' && (
        <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 font-medium text-gray-600">
          LLM: {llmAllowed ? 'yes' : 'no'}
        </span>
      )}
      {downgraded && (
        <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-medium text-amber-700">
          downgraded: {requestedMode} → {selectedMode}
        </span>
      )}
      {deepApproval && (
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${
            deepCopy?.className || 'border-gray-200 bg-white text-gray-600'
          }`}
          title={formatDeepApprovalTitle(deepApproval) || deepCopy?.description}
        >
          {deepCopy?.label || deepApproval.reason_code}
        </span>
      )}
      {reason && reason !== deepApproval?.reason_code && (
        <span
          className="inline-flex items-center rounded-full border border-gray-200 bg-white px-2 py-0.5 font-medium text-gray-500"
          title={reason}
        >
          {formatBudgetReason(reason)}
        </span>
      )}
    </div>
  )
}

const usageModeLabels = {
  none: 'manual',
  cheap: 'cheap',
  normal: 'normal',
  deep: 'deep',
}

const usageWarnings = {
  no_runtime_decisions_yet: 'no runtime decisions yet',
  runtime_mode_downgraded: 'some modes were downgraded by policy',
  deep_mode_downgraded: 'deep mode was downgraded',
  context_truncated: 'context was truncated',
}

const count = (value) => Number(value || 0)
const modes = ['none', 'cheap', 'normal', 'deep']

export function AgentRuntimeUsagePanel({ summary, compact = false }) {
  if (!summary) return null
  const selectedModes = summary.selected_modes || {}
  const runtimeDecisions = count(summary.runtime_decision_messages)
  const modelCalls = count(summary.llm_allowed_messages)
  const noModel = count(summary.no_model_messages)
  const deepDowngraded = count(summary.deep_downgraded_messages)
  const truncated = count(summary.context_truncated_messages)
  const warnings = Array.isArray(summary.warnings) ? summary.warnings : []

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-gray-900">Runtime usage</p>
          <p className="mt-1 text-xs leading-5 text-gray-500">
            Based on stored agent messages. This is runtime policy accounting, not provider billing.
          </p>
        </div>
        <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs font-medium text-gray-600">
          {runtimeDecisions} messages
        </span>
      </div>

      <div className={`mt-4 grid gap-2 ${compact ? 'grid-cols-2' : 'grid-cols-2 md:grid-cols-4'}`}>
        {modes.map((mode) => (
          <div key={mode} className={`rounded-xl border px-3 py-2 ${badgeClass(mode)}`}>
            <p className="text-[11px] font-semibold uppercase tracking-wide opacity-75">{usageModeLabels[mode]}</p>
            <p className="mt-1 text-lg font-bold">{count(selectedModes[mode])}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-gray-600 md:grid-cols-4">
        <div className="rounded-xl bg-gray-50 px-3 py-2">
          <p className="font-medium text-gray-900">LLM</p>
          <p>{modelCalls}</p>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2">
          <p className="font-medium text-gray-900">Manual</p>
          <p>{noModel}</p>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2">
          <p className="font-medium text-gray-900">Deep↓</p>
          <p>{deepDowngraded}</p>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2">
          <p className="font-medium text-gray-900">Truncated</p>
          <p>{truncated}</p>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {warnings.map((warning) => (
            <span key={warning} className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
              {usageWarnings[warning] || warning}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
