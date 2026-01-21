import { useState } from 'react'
import { Play, Loader, CheckCircle, XCircle } from 'lucide-react'
import clsx from 'clsx'

export default function BaseScanForm({
  fields = [],
  initialValues = {},
  onScan,
  loading = false,
  submitLabel = 'Run Scan',
  scanColor = 'blue'
}) {
  const [form, setForm] = useState(initialValues)
  const [localLoading, setLocalLoading] = useState(false)
  const [scanResult, setScanResult] = useState(null)

  const colorMap = {
    blue: { bg: 'bg-blue-100', text: 'text-blue-600', btn: 'bg-blue-600 hover:bg-blue-700', resBg: 'bg-blue-50', resBorder: 'border-blue-200', resText: 'text-blue-900' },
    green: { bg: 'bg-green-100', text: 'text-green-600', btn: 'bg-green-600 hover:bg-green-700', resBg: 'bg-green-50', resBorder: 'border-green-200', resText: 'text-green-900' },
    red: { bg: 'bg-red-100', text: 'text-red-600', btn: 'bg-red-600 hover:bg-red-700', resBg: 'bg-red-50', resBorder: 'border-red-200', resText: 'text-red-900' },
    purple: { bg: 'bg-purple-100', text: 'text-purple-600', btn: 'bg-purple-600 hover:bg-purple-700', resBg: 'bg-purple-50', resBorder: 'border-purple-200', resText: 'text-purple-900' },
    // можно добавить другие цвета по необходимости
  }

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async e => {
    e.preventDefault()
    const preparedData = { ...form }
    if (preparedData.targets && !Array.isArray(preparedData.targets)) {
      preparedData.targets = preparedData.targets
        .split('\n')
        .map(t => t.trim())
        .filter(Boolean)
    }

    try {
      setLocalLoading(true)
      const result = await onScan(preparedData)
      setScanResult(result) // реальный ответ API
    } catch (err) {
      setScanResult({
        status: 'error',
        message: err.message || 'Scan failed'
      })
    } finally {
      setLocalLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Всплывашка результата */}
      {scanResult && (
        <div className={clsx(
          'rounded-lg p-4 border flex items-start space-x-3',
          scanResult.status === 'success'
            ? 'bg-green-50 border border-green-200 text-green-900'
            : 'bg-red-50 border border-red-200 text-red-900'
        )}>
          {scanResult.status === 'success' ? (
            <CheckCircle className="flex-shrink-0 mt-0.5 text-green-600" size={20} />
          ) : (
            <XCircle className="flex-shrink-0 mt-0.5 text-red-600" size={20} />
          )}
          <div className="flex-1">
            <p className="font-medium">{scanResult.message}</p>
            {scanResult.results && (
              <pre className="mt-2 text-xs text-gray-700 bg-white p-3 rounded overflow-x-auto">
                {JSON.stringify(scanResult.results, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {fields.map(field => {
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
                    onChange={e => update(field.name, +e.target.value)}
                    placeholder={field.placeholder || ''}
                    className="w-full border p-2 rounded"
                  />
                </div>
              )
            default:
              return (
                <div key={field.name}>
                  <label className="block mb-1">{field.label}</label>
                  <input
                    type="text"
                    value={value}
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
          disabled={localLoading}
          className={clsx(
            'w-full flex items-center justify-center space-x-2 px-4 py-2 rounded text-white',
            colorMap[scanColor]?.btn,
            localLoading && 'opacity-50 cursor-not-allowed'
          )}
        >
          {localLoading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
          <span>{submitLabel}</span>
        </button>
      </form>
    </div>
  )
}
