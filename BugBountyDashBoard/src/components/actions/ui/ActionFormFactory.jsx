import { useState } from 'react'
import BaseActionForm from '../forms/BaseActionForm'
import { ACTIONS } from '@/components/actions/configs/actions.config'

export default function ActionFormFactory({ type, onRun, actionColor }) {
  const action = ACTIONS.find(s => s.form === type)
  const [loading, setLoading] = useState(false)

  if (!action) {
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
      fields={action.fields}
      initialValues={action.initialValues}
      onRun={handleAction}
      loading={loading}
      submitLabel={action.label || 'Run Action'}
      actionColor={actionColor || 'blue'}
    />
  )
}
