import { useState } from 'react'
import BaseActionForm from '../forms/BaseActionForm'
export default function ActionFormFactory({ action, type, onRun, actionColor, loading: parentLoading = false }) {
  const resolvedAction = action
  const [loading, setLoading] = useState(false)

  if (!resolvedAction) {
    return (
      <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Unknown action form: <b>{type}</b>
      </div>
    )
  }

  const handleAction = async (data) => {
    setLoading(true)
    try {
      const result = await onRun(data)
      return result
    } finally {
      setLoading(false)
    }
  }

  return (
    <BaseActionForm
      fields={resolvedAction.fields}
      initialValues={resolvedAction.initialValues}
      onRun={handleAction}
      loading={loading || parentLoading}
      submitLabel={resolvedAction.label || 'Run Action'}
      actionColor={actionColor || resolvedAction.color || 'blue'}
    />
  )
}
