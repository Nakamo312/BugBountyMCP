import React, { useEffect, useState } from 'react'
import { useProgram } from '../context/ProgramContext'
import { healthCheck, getHostsByProgram } from '../services/api'
import { Activity, Server, CheckCircle, AlertCircle, Loader } from 'lucide-react'

const Dashboard = () => {
  const { selectedProgram } = useProgram()
  const [healthStatus, setHealthStatus] = useState(null)
  const [hostsCount, setHostsCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkHealth()
  }, [])

  useEffect(() => {
    if (selectedProgram) {
      loadHostsCount()
    }
  }, [selectedProgram])

  const checkHealth = async () => {
    try {
      await healthCheck()
      setHealthStatus('healthy')
    } catch (error) {
      setHealthStatus('unhealthy')
    } finally {
      setLoading(false)
    }
  }

  const loadHostsCount = async () => {
    try {
      const response = await getHostsByProgram(selectedProgram.id, { limit: 1 })
      setHostsCount(response.data.total || 0)
    } catch (error) {
      console.error('Failed to load hosts count:', error)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader className="animate-spin text-primary-500" size={32} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-2">Overview of your bug bounty program</p>
      </div>

      {/* Health Status */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Activity className={healthStatus === 'healthy' ? 'text-green-500' : 'text-red-500'} size={24} />
            <div>
              <h3 className="font-semibold text-gray-900">API Status</h3>
              <p className="text-sm text-gray-600">
                {healthStatus === 'healthy' ? 'All systems operational' : 'API connection failed'}
              </p>
            </div>
          </div>
          {healthStatus === 'healthy' ? (
            <CheckCircle className="text-green-500" size={24} />
          ) : (
            <AlertCircle className="text-red-500" size={24} />
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Active Program</p>
              <p className="text-2xl font-bold text-gray-900 mt-2">
                {selectedProgram?.name || 'None'}
              </p>
            </div>
            <Server className="text-primary-500" size={32} />
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Hosts</p>
              <p className="text-2xl font-bold text-gray-900 mt-2">
                {hostsCount}
              </p>
            </div>
            <Server className="text-green-500" size={32} />
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Quick Actions</p>
              <p className="text-sm text-gray-600 mt-2">
                Start scanning
              </p>
            </div>
            <Activity className="text-blue-500" size={32} />
          </div>
        </div>
      </div>

      {!selectedProgram && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
          <div className="flex items-center space-x-3">
            <AlertCircle className="text-yellow-600" size={24} />
            <div>
              <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
              <p className="text-sm text-yellow-700 mt-1">
                Please select a program from the sidebar or create a new one in the Programs page.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Dashboard
