import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ProgramProvider } from './context/ProgramContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Programs from './pages/Programs'
import Hosts from './pages/Hosts'
import Analysis from './pages/Analysis'
import SurfaceComponents from './pages/SurfaceComponents'
import Workbench from './pages/Workbench'
import AgentWorkspace from './pages/AgentWorkspace'
import AgentTaskDetailPage from './pages/AgentTaskDetail'
import ActionsPage from './pages/Actions/ActionPage'
import PlaceholderPage from './pages/Placeholder'

function App() {
  return (
    <ProgramProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/program-overview" element={<Dashboard />} />
            <Route path="/programs" element={<Programs />} />
            <Route path="/actions" element={<ActionsPage />} />
            <Route path="/workbench" element={<Workbench />} />
            <Route path="/execution" element={<AgentWorkspace />} />
            <Route path="/execution/tasks/:taskId" element={<AgentTaskDetailPage />} />
            <Route path="/workspace" element={<AgentWorkspace />} />
            <Route path="/workspace/tasks/:taskId" element={<AgentTaskDetailPage />} />
            <Route path="/hosts" element={<Hosts />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/graph/components" element={<SurfaceComponents />} />
            <Route path="/surface-components" element={<SurfaceComponents />} />
            <Route path="/graph/pipeline" element={<Dashboard focus="projection" />} />
            <Route
              path="/knowledge/evidence"
              element={(
                <PlaceholderPage
                  title="Evidence"
                  description="Evidence paths are available in Workbench and Neo4j evidence lenses."
                />
              )}
            />
            <Route
              path="/knowledge/search"
              element={(
                <PlaceholderPage
                  title="Search Index"
                  description="Search projection status is reported from Program Overview."
                  primaryPath="/"
                  primaryLabel="Open Program Overview"
                />
              )}
            />
          </Routes>
        </Layout>
      </Router>
    </ProgramProvider>
  )
}

export default App
