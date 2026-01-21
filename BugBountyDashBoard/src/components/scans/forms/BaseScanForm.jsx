import { useState } from 'react'
import { Play, Loader } from 'lucide-react'
import clsx from 'clsx'

const colorMap = {
  blue: { bg: 'bg-blue-100', text: 'text-blue-600' },
  green: { bg: 'bg-green-100', text: 'text-green-600' },
  red: { bg: 'bg-red-100', text: 'text-red-600' },
  purple: { bg: 'bg-purple-100', text: 'text-purple-600' },
}

export default function BaseScanForm({
  fields = [],
  initialValues = {},
  onScan,
  loading = false,
  submitLabel = 'Run Scan',
  scanColor = 'blue',
}) {
  const [form, setForm] = useState(initialValues)

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = e => {
    e.preventDefault() 
    const preparedData = { ...form }
    if (preparedData.targets && !Array.isArray(preparedData.targets)) {
      preparedData.targets = preparedData.targets
        .split('\n')
        .map(t => t.trim())
        .filter(Boolean)
    }
    onScan(preparedData)
  }

  const colors = colorMap[scanColor] || { bg: 'bg-gray-100', text: 'text-gray-600' }

  return (
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
        disabled={loading}
        className={clsx(
          'w-full flex items-center justify-center gap-2 px-4 py-2 rounded text-white',
          loading ? 'opacity-50 cursor-not-allowed' : colors.bg
        )}
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>{submitLabel}</span>
      </button>
    </form>
  )
}
