import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useProgram } from '../context/ProgramContext'
import { 
  LayoutDashboard, 
  FolderKanban, 
  Scan, 
  Server,
  AlertCircle 
} from 'lucide-react'
import ProgramSelector from './ProgramSelector'

const Layout = ({ children }) => {
  const location = useLocation()
  const { selectedProgram } = useProgram()

  const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/programs', icon: FolderKanban, label: 'Programs' },
    { path: '/scans', icon: Scan, label: 'Scans' },
    { path: '/hosts', icon: Server, label: 'Hosts' },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-950">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 bg-gray-900/80 backdrop-blur-sm border-r border-gray-800 text-white">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-gray-800">
            <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              Bug Bounty Dashboard
            </h1>
          </div>

          {/* Program Selector */}
          <div className="p-4 border-b border-gray-800">
            <ProgramSelector />
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`
                    flex items-center space-x-3 px-4 py-3 rounded-lg transition-all
                    ${isActive 
                      ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 text-white' 
                      : 'text-gray-400 hover:bg-gray-800/50 hover:text-white border border-transparent'
                    }
                  `}
                >
                  <Icon size={20} />
                  <span className="font-medium">{item.label}</span>
                </Link>
              )
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-gray-800 text-sm text-gray-500">
            <div className="flex items-center space-x-2">
              <AlertCircle size={16} />
              <span>API v0.1.0</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="ml-64 p-8">
        {children}
      </main>
    </div>
  )
}

export default Layout