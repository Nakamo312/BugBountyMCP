import React from 'react'
import { AlertCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function PlaceholderPage({ title, description, primaryPath = '/workbench', primaryLabel = 'Open Workbench' }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-1 text-gray-400" size={22} />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">{description}</p>
          <Link
            to={primaryPath}
            className="mt-5 inline-flex rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-800"
          >
            {primaryLabel}
          </Link>
        </div>
      </div>
    </div>
  )
}
