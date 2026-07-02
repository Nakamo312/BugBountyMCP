import React from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowLeft, Loader } from 'lucide-react'
import { Badge } from '../AgentCards'
import { formatStatus, shortId, statusClass } from '../agentDisplay'

export function AgentTaskHeader({ loading, onRefresh, task }) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <Link to="/execution" className="inline-flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-700">
          <ArrowLeft size={16} /> Back to Execution
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-900">{task?.title || 'Agent task'}</h1>
          <Badge className={statusClass(task?.status)}>{formatStatus(task?.status)}</Badge>
          <Badge className="border-gray-200 bg-gray-50 text-gray-600">#{shortId(task?.task_id)}</Badge>
        </div>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Activity size={16} />} Refresh
      </button>
    </div>
  )
}
