import React from 'react'
import { PlayCircle, XCircle } from 'lucide-react'
import { parseTargetList } from './agentDisplay'

export const ExperienceTargetForm = ({ proposal, value, error, busy, onChange, onSubmit, onCancel }) => {
  const targets = parseTargetList(value)
  return (
    <form onSubmit={onSubmit} className="rounded-2xl border border-violet-200 bg-violet-50/60 p-4 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h4 className="font-semibold text-gray-900">Targets для {proposal.capability_id}/{proposal.profile_id}</h4>
          <p className="mt-1 text-xs leading-5 text-gray-600">
            Введи scope перед созданием ActionRequest. Значения разделяются запятыми.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-lg border border-violet-200 bg-white px-3 py-1.5 text-xs font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50"
        >
          <XCircle size={14} /> Отмена
        </button>
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={3}
        placeholder="https://example.com, api.example.com/v1/users, *.example.com"
        className="mt-3 w-full resize-none rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
      />
      {error && <p className="mt-2 text-xs font-medium text-red-700">{error}</p>}
      <div className="mt-3 rounded-xl bg-white px-3 py-2 text-xs text-gray-600">
        Preview: {targets.length > 0 ? targets.join(' · ') : 'targets не заданы'}
      </div>
      <button
        type="submit"
        disabled={busy || targets.length === 0}
        className="mt-3 inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
      >
        <PlayCircle size={15} /> Создать ActionRequest
      </button>
    </form>
  )
}
