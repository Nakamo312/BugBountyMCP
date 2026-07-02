import React from 'react'
import { StatusBadge } from './StatusBadge'
import { severityBadgeClass } from './dashboardUi'

const OperatorPlanStep = ({ step }) => (
  <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="font-semibold text-gray-900">{step.title}</h4>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${severityBadgeClass(step.severity)}`}>
            {step.severity}
          </span>
          {step.blocks_ui_freshness && (
            <span className="rounded-full bg-purple-100 px-2 py-0.5 text-xs font-semibold text-purple-800">
              blocks UI freshness
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-600">{step.reason}</p>
        <div className="mt-1 text-xs text-gray-500">
          {step.step_id} · {step.area}
        </div>
      </div>
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        priority {step.priority}
      </div>
    </div>
    {step.commands?.length > 0 && (
      <details className="mt-3 rounded border border-gray-200 bg-white p-3">
        <summary className="cursor-pointer text-xs font-semibold text-gray-600">Advanced local CLI fallback</summary>
        <div className="mt-2 space-y-2">
          {step.commands.map((command) => (
            <code key={command} className="block overflow-x-auto rounded bg-gray-900 px-3 py-2 text-xs text-gray-100">
              {command}
            </code>
          ))}
        </div>
      </details>
    )}
  </div>
)

export const OperatorPlan = ({ plan }) => {
  if (!plan) return null

  const steps = plan.steps || []

  return (
    <div className="mt-5 rounded-lg border border-blue-100 bg-blue-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-blue-950">Operator plan</h3>
          <p className="mt-1 text-sm text-blue-800">
            Projection readiness from backend read models.
          </p>
        </div>
        <StatusBadge ok={plan.ui_data_fresh} label={plan.ui_data_fresh ? 'fresh' : `${plan.step_count || 0} steps`} />
      </div>

      {plan.next_step && (
        <div className="mt-4 rounded-lg border border-blue-200 bg-white p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-500">Next step</div>
          <OperatorPlanStep step={plan.next_step} />
        </div>
      )}

      {steps.length > 1 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-blue-900">Show all operator steps</summary>
          <div className="mt-3 space-y-3">
            {steps.map((step) => (
              <OperatorPlanStep key={step.step_id} step={step} />
            ))}
          </div>
        </details>
      )}

      {steps.length === 0 && (
        <p className="mt-3 text-sm text-blue-800">No pending steps.</p>
      )}
    </div>
  )
}
