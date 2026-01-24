import React from 'react'
import { Server, Globe, Link, FileText, Hash } from 'lucide-react'

const StatCard = ({ label, value, icon: Icon, color = 'primary' }) => {
  const colorClasses = {
    primary: 'text-primary-500',
    green: 'text-green-500',
    blue: 'text-blue-500',
    purple: 'text-purple-500',
    orange: 'text-orange-500',
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
        </div>
        <Icon className={colorClasses[color]} size={32} />
      </div>
    </div>
  )
}

const HostStats = ({ programStats, hosts, filteredCount }) => {
  if (!programStats) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Total Hosts" value={hosts.length} icon={Server} color="primary" />
        <StatCard
          label="In Scope"
          value={hosts.filter(h => h.in_scope).length}
          icon={Globe}
          color="green"
        />
        <StatCard label="Visible" value={filteredCount} icon={Server} color="blue" />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      <StatCard
        label="Total Hosts"
        value={programStats.total_hosts || 0}
        icon={Server}
        color="primary"
      />
      <StatCard
        label="In Scope"
        value={programStats.in_scope_hosts || 0}
        icon={Globe}
        color="green"
      />
      <StatCard
        label="Endpoints"
        value={programStats.total_endpoints || 0}
        icon={Link}
        color="blue"
      />
      <StatCard
        label="Parameters"
        value={programStats.total_parameters || 0}
        icon={Hash}
        color="purple"
      />
      <StatCard
        label="With Body"
        value={programStats.endpoints_with_body || 0}
        icon={FileText}
        color="orange"
      />
    </div>
  )
}

export default HostStats
