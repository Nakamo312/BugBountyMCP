import { useState } from 'react'
import { CheckCircle, XCircle, Loader } from 'lucide-react'
import clsx from 'clsx'

export default function BaseScanForm({
  fields = [],
  initialValues = {},
  onScan,
  loading = false,
  submitLabel = 'Run Scan',
  scanColor = 'blue',
}) {
  const [form, setForm] = useState(initialValues)
  const [scanStatus, setScanStatus] = useState(null)

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setScanStatus(null)
    const preparedData = { ...form }

    if (preparedData.targets && !Array.isArray(preparedData.targets)) {
      preparedData.targets = preparedData.targets
        .split('\n')
        .map(t => t.trim())
        .filter(Boolean)
    }

    try {
      setScanStatus({ status: 'loading', message: 'Running scan...' })
      const result = await onScan(preparedData)
      setScanStatus({
        status: 'success',
        message: result?.message || 'Scan completed successfully!',
        results: result?.results || null,
      })
    } catch (err) {
      setScanStatus({
        status: 'error',
        message: err?.message || 'Scan failed',
      })
    }
  }
  const colorMap = {
    blue: 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-400 text-white',
    green: 'bg-green-600 hover:bg-green-700 focus:ring-green-400 text-white',
    red: 'bg-red-600 hover:bg-red-700 focus:ring-red-400 text-white',
    yellow: 'bg-yellow-600 hover:bg-yellow-700 focus:ring-yellow-400 text-white',
    purple: 'bg-purple-600 hover:bg-purple-700 focus:ring-purple-400 text-white',
    pink: 'bg-pink-600 hover:bg-pink-700 focus:ring-pink-400 text-white',
    orange: 'bg-orange-600 hover:bg-orange-700 focus:ring-orange-400 text-white',
    teal: 'bg-teal-600 hover:bg-teal-700 focus:ring-teal-400 text-white',
    cyan: 'bg-cyan-600 hover:bg-cyan-700 focus:ring-cyan-400 text-white',
    violet: 'bg-violet-600 hover:bg-violet-700 focus:ring-violet-400 text-white',
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {fields.map((field) => {
        const value = form[field.name] ?? ''
        switch (field.type) {
          case 'textarea':
            return (
              <div key={field.name}>
                <label className="block mb-1 font-medium">{field.label}</label>
                <textarea
                  value={value}
                  onChange={(e) => update(field.name, e.target.value)}
                  rows={field.rows || 3}
                  placeholder={field.placeholder || ''}
                  className="w-full border border-gray-300 p-2 rounded focus:ring-2 focus:ring-primary-500"
                />
              </div>
            )
          case 'checkbox':
            return (
              <label key={field.name} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!value}
                  onChange={(e) => update(field.name, e.target.checked)}
                  className="form-checkbox"
                />
                {field.label}
              </label>
            )
          case 'number':
            return (
              <div key={field.name}>
                <label className="block mb-1 font-medium">{field.label}</label>
                <input
                  type="number"
                  value={value}
                  onChange={(e) => update(field.name, +e.target.value)}
                  placeholder={field.placeholder || ''}
                  className="w-full border border-gray-300 p-2 rounded focus:ring-2 focus:ring-primary-500"
                />
              </div>
            )
          default:
            return (
              <div key={field.name}>
                <label className="block mb-1 font-medium">{field.label}</label>
                <input
                  type="text"
                  value={value}
                  onChange={(e) => update(field.name, e.target.value)}
                  placeholder={field.placeholder || ''}
                  className="w-full border border-gray-300 p-2 rounded focus:ring-2 focus:ring-primary-500"
                />
              </div>
            )
        }
      })}

      {/* Кнопка */}
      <button
        type="submit"
        disabled={loading}
        className={clsx(
          'w-full flex items-center justify-center gap-2 px-4 py-2 rounded font-medium transition-colors focus:ring-2',
          colorMap[scanColor] || colorMap.blue,
          loading && 'opacity-50 cursor-not-allowed'
        )}
      >
        {loading ? <Loader className="animate-spin" size={16} /> : null}
        <span>{submitLabel}</span>
      </button>

      {/* Всплывающий статус */}
      {scanStatus && (
        <div
          className={clsx(
            'flex items-center gap-2 p-3 rounded text-sm mt-2',
            scanStatus.status === 'success'
              ? 'bg-green-50 text-green-800'
              : scanStatus.status === 'error'
              ? 'bg-red-50 text-red-800'
              : 'bg-blue-50 text-blue-800'
          )}
        >
          {scanStatus.status === 'success' && <CheckCircle className="text-green-600" size={16} />}
          {scanStatus.status === 'error' && <XCircle className="text-red-600" size={16} />}
          {scanStatus.status === 'loading' && <Loader className="animate-spin" size={16} />}
          <span>{scanStatus.message}</span>
        </div>
      )}

      {/* Вывод raw результатов, если есть */}
      {scanStatus?.results && (
        <pre className="mt-2 text-xs text-gray-700 bg-white p-3 rounded overflow-x-auto">
          {JSON.stringify(scanStatus.results, null, 2)}
        </pre>
      )}
    </form>
  )
}
