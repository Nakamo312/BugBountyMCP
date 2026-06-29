import React from 'react'
import { Activity, AlertCircle, CheckCircle, Loader, Search, Server } from 'lucide-react'

const StatCard = ({ icon: Icon, iconClass, label, value }) => (
  <div className="rounded-lg bg-white p-6 shadow">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-gray-600">{label}</p>
        <p className="mt-2 text-2xl font-bold text-gray-900">{value}</p>
      </div>
      <Icon className={iconClass} size={32} />
    </div>
  </div>
)

export const DashboardLoading = () => (
  <div className="flex h-64 items-center justify-center">
    <Loader className="animate-spin text-primary-500" size={32} />
  </div>
)

export const ApiStatusCard = ({ healthStatus }) => {
  const healthy = healthStatus === 'healthy'
  const StatusIcon = healthy ? CheckCircle : AlertCircle
  return (
    <div className="rounded-lg bg-white p-6 shadow">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <Activity className={healthy ? 'text-green-500' : 'text-red-500'} size={24} />
          <div>
            <h3 className="font-semibold text-gray-900">API Status</h3>
            <p className="text-sm text-gray-600">{healthy ? 'All systems operational' : 'API connection failed'}</p>
          </div>
        </div>
        <StatusIcon className={healthy ? 'text-green-500' : 'text-red-500'} size={24} />
      </div>
    </div>
  )
}

export const DashboardStatCards = ({ hostsCount, overview, selectedProgram }) => (
  <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
    <StatCard icon={Server} iconClass="text-primary-500" label="Active Program" value={selectedProgram?.name || 'None'} />
    <StatCard icon={Server} iconClass="text-green-500" label="Total Hosts" value={hostsCount} />
    <StatCard
      icon={Search}
      iconClass="text-blue-500"
      label="Pending Experience Proposals"
      value={overview?.experience_proposals?.pending ?? 0}
    />
  </div>
)

export const NoProgramSelected = () => (
  <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-6">
    <div className="flex items-center space-x-3">
      <AlertCircle className="text-yellow-600" size={24} />
      <div>
        <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
        <p className="mt-1 text-sm text-yellow-700">Select a program to view hosts, projection health, and analysis state.</p>
      </div>
    </div>
  </div>
)
