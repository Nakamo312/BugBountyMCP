import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ProgramProvider } from './context/ProgramContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Programs from './pages/Programs'
import Scans from './pages/Scans'
import Hosts from './pages/Hosts'

function App() {
  return (
    <ProgramProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/programs" element={<Programs />} />
            <Route path="/scans" element={<Scans />} />
            <Route path="/hosts" element={<Hosts />} />
          </Routes>
        </Layout>
      </Router>
    </ProgramProvider>
  )
}

export default App
