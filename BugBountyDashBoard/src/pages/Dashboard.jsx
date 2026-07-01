import React from 'react'
import { useProgram } from '../context/ProgramContext'
import {
  ApiStatusCard,
  DashboardLoading,
  DashboardStatCards,
  NoProgramSelected,
  ProjectionOverview,
} from '../components/dashboard'
import { useDashboardOverview } from '../hooks/useDashboardOverview'

const Dashboard = () => {
  const { selectedProgram } = useProgram()
  const {
    healthStatus,
    hostsCount,
    loading,
    loadProjectionOverview,
    operatorPlan,
    overview,
    overviewError,
    overviewLoading,
    programSummary,
  } = useDashboardOverview(selectedProgram)

  if (loading) return <DashboardLoading />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Program Overview</h1>
        <p className="mt-2 text-gray-600">{programSummary}</p>
      </div>

      <ApiStatusCard healthStatus={healthStatus} />
      <DashboardStatCards hostsCount={hostsCount} overview={overview} selectedProgram={selectedProgram} />

      {selectedProgram && (
        <ProjectionOverview
          overview={overview}
          loading={overviewLoading}
          error={overviewError}
          operatorPlan={operatorPlan}
          onRefresh={loadProjectionOverview}
        />
      )}

      {!selectedProgram && <NoProgramSelected />}
    </div>
  )
}

export default Dashboard
