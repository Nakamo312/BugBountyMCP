import { useState } from 'react'

export default function BaseScanForm({ fields = [], initialValues = {}, onScan, loading = false, submitLabel = 'Run Scan' }) {
  const [form, setForm] = useState(initialValues)

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = e => {
    e.preventDefault()
    onScan(form)
  }

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
        className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
      >
        {loading ? 'Running...' : submitLabel}
      </button>
    </form>
  )
}
