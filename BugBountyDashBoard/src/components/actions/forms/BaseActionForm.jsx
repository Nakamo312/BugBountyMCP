import { useEffect, useState } from 'react'
import { Play, Loader, CheckCircle, XCircle } from 'lucide-react'
import clsx from 'clsx'

export default function BaseActionForm({
  fields = [],
  initialValues = {},
  onRun,
  loading = false,
  submitLabel = 'Run Action',
  actionColor = 'blue'
}) {
  const [form, setForm] = useState(initialValues)
  const [localLoading, setLocalLoading] = useState(false)
  const [actionResult, setActionResult] = useState(null)

  useEffect(() => {
    setForm(initialValues)
  }, [initialValues])

  const colorMap = {
    blue: { bg: 'bg-blue-100', text: 'text-blue-600', btn: 'bg-blue-600 hover:bg-blue-700', resBg: 'bg-blue-50', resBorder: 'border-blue-200', resText: 'text-blue-900' },
    green: { bg: 'bg-green-100', text: 'text-green-600', btn: 'bg-green-600 hover:bg-green-700', resBg: 'bg-green-50', resBorder: 'border-green-200', resText: 'text-green-900' },
    red: { bg: 'bg-red-100', text: 'text-red-600', btn: 'bg-red-600 hover:bg-red-700', resBg: 'bg-red-50', resBorder: 'border-red-200', resText: 'text-red-900' },
    purple: { bg: 'bg-purple-100', text: 'text-purple-600', btn: 'bg-purple-600 hover:bg-purple-700', resBg: 'bg-purple-50', resBorder: 'border-purple-200', resText: 'text-purple-900' },
    indigo: { btn: 'bg-indigo-600 hover:bg-indigo-700' },
    pink: { btn: 'bg-pink-600 hover:bg-pink-700' },
    yellow: { btn: 'bg-yellow-600 hover:bg-yellow-700' },
    orange: { btn: 'bg-orange-600 hover:bg-orange-700' },
    cyan: { btn: 'bg-cyan-600 hover:bg-cyan-700' },
    teal: { btn: 'bg-teal-600 hover:bg-teal-700' },
    rose: { btn: 'bg-rose-600 hover:bg-rose-700' },
    violet: { btn: 'bg-violet-600 hover:bg-violet-700' },
    slate: { btn: 'bg-slate-600 hover:bg-slate-700' },
    amber: { btn: 'bg-amber-600 hover:bg-amber-700' },
  }

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async e => {
    e.preventDefault()
    const preparedData = { ...form }
    fields.forEach(field => {
      if (field.asArray && preparedData[field.name] && !Array.isArray(preparedData[field.name])) {
        preparedData[field.name] = preparedData[field.name]
          .split('\n')
          .map(t => t.trim())
          .filter(Boolean)
      }
    })

    try {
      setLocalLoading(true)
      const result = await onRun(preparedData)
      setActionResult(result) // API response
    } catch (err) {
      setActionResult({
        status: 'error',
        message: err.message || 'Action failed'
      })
    } finally {
      setLocalLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Result toast */}
      {actionResult && (
        <div className={clsx(
          'rounded-lg p-4 border flex items-start space-x-3',
          actionResult.status === 'success'
            ? 'bg-green-50 border border-green-200 text-green-900'
            : 'bg-red-50 border border-red-200 text-red-900'
        )}>
          {actionResult.status === 'success' ? (
            <CheckCircle className="flex-shrink-0 mt-0.5 text-green-600" size={20} />
          ) : (
            <XCircle className="flex-shrink-0 mt-0.5 text-red-600" size={20} />
          )}
          <div className="flex-1">
            <p className="font-medium">{actionResult.message}</p>
            {actionResult.results && (
              <pre className="mt-2 text-xs text-gray-700 bg-white p-3 rounded overflow-x-auto">
                {JSON.stringify(actionResult.results, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {fields.map(field => {
          if (field.dependsOn && form[field.dependsOn.field] !== field.dependsOn.value) return null

          const value = form[field.name] ?? ''
          switch (field.type) {
            case 'textarea':
              return (
                <div key={field.name}>
                  <label className="block mb-1">{field.label}</label>
                  <textarea
                    value={value}
                    onChange={e => update(field.name, e.target.value)}
                    rows={field.rows || 3}
                    placeholder={field.placeholder || ''}
                    required={field.required}
                    className="w-full border p-2 rounded"
                  />
                </div>
              )
            case 'checkbox':
              return (
                <label key={field.name} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={!!value}
                    onChange={e => update(field.name, e.target.checked)}
                    className="rounded"
                  />
                  {field.label}
                </label>
              )
            case 'number':
              return (
                <div key={field.name}>
                  <label className="block mb-1">{field.label}</label>
                  <input
                    type="number"
                    value={value}
                    min={field.min}
                    max={field.max}
                    required={field.required}
                    onChange={e => update(field.name, e.target.value === '' ? '' : Number(e.target.value))}
                    placeholder={field.placeholder || ''}
                    className="w-full border p-2 rounded"
                  />
                </div>
              )
            case 'select':
              return (
                <div key={field.name}>
                  <label className="block mb-1">{field.label}</label>
                  <select
                    value={value}
                    required={field.required}
                    onChange={e => update(field.name, e.target.value)}
                    className="w-full border p-2 rounded bg-white"
                  >
                    {(field.options || []).map(option => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </div>
              )
            default:
              return (
                <div key={field.name}>
                  <label className="block mb-1">{field.label}</label>
                  <input
                    type="text"
                    value={value}
                    required={field.required}
                    onChange={e => update(field.name, e.target.value)}
                    placeholder={field.placeholder || ''}
                    className="w-full border p-2 rounded"
                  />
                </div>
              )
          }
        })}

        <button
          type="submit"
          disabled={localLoading || loading}
          className={clsx(
            'w-full flex items-center justify-center space-x-2 px-4 py-2 rounded text-white',
            colorMap[actionColor]?.btn || 'bg-blue-600 hover:bg-blue-700',
            (localLoading || loading) && 'opacity-50 cursor-not-allowed'
          )}
        >
          {localLoading || loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
          <span>{submitLabel}</span>
        </button>
      </form>
    </div>
  )
}
