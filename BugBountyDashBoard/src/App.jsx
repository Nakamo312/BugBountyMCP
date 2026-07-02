import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { ProgramProvider } from './context/ProgramContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Programs from './pages/Programs'
import Workbench from './pages/Workbench'
import AgentWorkspace from './pages/AgentWorkspace'
import AgentTaskDetailPage from './pages/AgentTaskDetail'
import ActionsPage from './pages/Actions/ActionPage'

const RedirectToWorkbenchLens = ({ lens, diagnostics }) => {
  const query = new URLSearchParams()
  if (lens) query.set('lens', lens)
  if (diagnostics) query.set('diagnostics', diagnostics)
  return <Navigate to={`/workbench?${query.toString()}`} replace />
}

const WorkspaceTaskRedirect = () => {
  const { taskId } = useParams()
  return <Navigate to={`/execution/tasks/${taskId}`} replace />
}

function App() {
  return (
    <ProgramProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/program-overview" element={<Navigate to="/" replace />} />
            <Route path="/programs" element={<Programs />} />
            <Route path="/actions" element={<ActionsPage />} />
            <Route path="/workbench" element={<Workbench />} />
            <Route path="/execution" element={<AgentWorkspace />} />
            <Route path="/execution/tasks/:taskId" element={<AgentTaskDetailPage />} />

            <Route path="/workspace" element={<Navigate to="/execution" replace />} />
            <Route path="/workspace/tasks/:taskId" element={<WorkspaceTaskRedirect />} />
            <Route path="/hosts" element={<RedirectToWorkbenchLens lens="surface" />} />
            <Route path="/analysis" element={<RedirectToWorkbenchLens lens="coverage" />} />
            <Route path="/graph/components" element={<RedirectToWorkbenchLens lens="components" />} />
            <Route path="/surface-components" element={<RedirectToWorkbenchLens lens="components" />} />
            <Route path="/graph/pipeline" element={<RedirectToWorkbenchLens diagnostics="projection" />} />
            <Route path="/knowledge/evidence" element={<RedirectToWorkbenchLens lens="neo4j_evidence" />} />
            <Route path="/knowledge/search" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </Router>
    </ProgramProvider>
  )
}

export default App
