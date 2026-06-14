import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ProgramProvider } from './context/ProgramContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Programs from './pages/Programs'
import Hosts from './pages/Hosts'
import Analysis from './pages/Analysis'
import InfrastructureMap from './pages/InfrastructureMap'
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
            <Route path="/hosts" element={<Hosts />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/infrastructure" element={<InfrastructureMap />} />
          </Routes>
        </Layout>
      </Router>
    </ProgramProvider>
  )
}

export default App
