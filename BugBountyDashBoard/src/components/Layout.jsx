import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useProgram } from '../context/ProgramContext'
import {
  LayoutDashboard,
  FolderKanban,
  Scan,
  Server,
  ShieldAlert,
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
    { path: '/analysis', icon: ShieldAlert, label: 'Analysis' },
  ]

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 bg-gray-900 text-white shadow-lg">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-gray-800">
            <h1 className="text-xl font-bold text-primary-400">Bug Bounty Dashboard</h1>
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
                    flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors
                    ${isActive 
                      ? 'bg-primary-600 text-white' 
                      : 'text-gray-300 hover:bg-gray-800 hover:text-white'
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
          <div className="p-4 border-t border-gray-800 text-sm text-gray-400">
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
