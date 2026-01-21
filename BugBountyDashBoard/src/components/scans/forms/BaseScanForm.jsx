import { useState } from 'react'
import { CheckCircle, XCircle } from 'lucide-react'
import clsx from 'clsx'

export default function BaseScanForm({ fields = [], initialValues = {}, onScan, loading = false, submitLabel = 'Run Scan', scanColor = 'blue' }) {
  const [form, setForm] = useState(initialValues)
  const [scanResult, setScanResult] = useState(null)
  const [localLoading, setLocalLoading] = useState(false)

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
      setScanResult(result) 
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
    <div className="space-y-4 relative">
      {/* Всплывашка результата */}
      {scanResult && (
        <div
          className={clsx(
            'flex items-start space-x-2 p-3 rounded border',
            scanResult.status === 'success' ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'
          )}
        >
          {scanResult.status === 'success' ? (
            <CheckCircle className="mt-0.5" size={20} />
          ) : (
            <XCircle className="mt-0.5" size={20} />
          )}
          <div>
            <p className="font-medium">{scanResult.message}</p>
            {scanResult.results && (
              <pre className="mt-1 text-xs text-gray-700 bg-white p-2 rounded overflow-x-auto">
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
                    className="form-checkbox"
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
            scanColor === 'blue' && 'bg-blue-600 hover:bg-blue-700',
            scanColor === 'green' && 'bg-green-600 hover:bg-green-700',
            scanColor === 'red' && 'bg-red-600 hover:bg-red-700',
            scanColor === 'purple' && 'bg-purple-600 hover:bg-purple-700',
            localLoading && 'opacity-50 cursor-not-allowed'
          )}
        >
          {localLoading ? (
            <span className="animate-spin">⏳</span>
          ) : (
            <span>▶️</span>
          )}
          <span>{submitLabel}</span>
        </button>
      </form>
    </div>
  )
}
