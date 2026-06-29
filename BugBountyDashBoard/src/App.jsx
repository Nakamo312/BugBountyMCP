import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ProgramProvider } from './context/ProgramContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Programs from './pages/Programs'
import Hosts from './pages/Hosts'
import Analysis from './pages/Analysis'
import InfrastructureMap from './pages/InfrastructureMap'
import SurfaceComponents from './pages/SurfaceComponents'
import AgentWorkspace from './pages/AgentWorkspace'
import AgentTaskDetailPage from './pages/AgentTaskDetail'
import ActionsPage from './pages/Actions/ActionPage'

function App() {
  return (
    <ProgramProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/programs" element={<Programs />} />
            <Route path="/actions" element={<ActionsPage />} />
            <Route path="/workspace" element={<AgentWorkspace />} />
            <Route path="/workspace/tasks/:taskId" element={<AgentTaskDetailPage />} />
            <Route path="/hosts" element={<Hosts />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/infrastructure" element={<InfrastructureMap />} />
            <Route path="/surface-components" element={<SurfaceComponents />} />
          </Routes>
        </Layout>
      </Router>
    </ProgramProvider>
  )
}

export default App
