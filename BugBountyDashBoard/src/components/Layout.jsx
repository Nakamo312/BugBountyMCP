import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useProgram } from '../context/ProgramContext'
import { 
  LayoutDashboard, 
  FolderKanban, 
  Scan, 
  Server,
  AlertCircle,
  Shield,
  Zap,
  GitBranch
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
    { path: '/vulnerabilities', icon: Shield, label: 'Vulnerabilities' },
    { path: '/reports', icon: GitBranch, label: 'Reports' },
    { path: '/monitoring', icon: Zap, label: 'Monitoring' },
  ]

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 bg-gray-900 border-r border-gray-800 shadow-xl">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-gray-800">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                <Shield size={20} className="text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">BugBounty</h1>
                <p className="text-xs text-gray-400">Security Dashboard</p>
              </div>
            </div>
          </div>

          {/* Program Selector */}
          <div className="p-4 border-b border-gray-800">
            <ProgramSelector />
            
            {/* Selected Program Info */}
            {selectedProgram && (
              <div className="mt-4 p-3 bg-gray-800 rounded-lg">
                <p className="text-sm font-medium text-white truncate">
                  {selectedProgram.name}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Scope: {selectedProgram.scope_count || 0} targets
                </p>
              </div>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path || 
                              (item.path !== '/' && location.pathname.startsWith(item.path))
              
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`
                    flex items-center space-x-3 px-4 py-3 rounded-lg transition-all
                    ${isActive 
                      ? 'bg-primary-900/30 text-primary-300 border-l-4 border-primary-500' 
                      : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200 border-l-4 border-transparent'
                    }
                  `}
                >
                  <Icon size={20} className={isActive ? 'text-primary-400' : ''} />
                  <span className="font-medium">{item.label}</span>
                  {isActive && (
                    <div className="ml-auto w-2 h-2 bg-primary-500 rounded-full"></div>
                  )}
                </Link>
              )
            })}
          </nav>

          {/* User/Status */}
          <div className="p-4 border-t border-gray-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center">
                  <span className="text-xs font-bold text-gray-300">AD</span>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-200">Admin</p>
                  <p className="text-xs text-gray-500">Security Team</p>
                </div>
              </div>
              
              {/* Status Indicator */}
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-xs text-gray-400">Online</span>
              </div>
            </div>
            
            {/* API Version */}
            <div className="mt-4 pt-3 border-t border-gray-800">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2 text-gray-500">
                  <AlertCircle size={12} />
                  <span>API v0.1.0</span>
                </div>
                <span className="px-2 py-1 bg-gray-800 rounded text-gray-400">
                  {new Date().toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="ml-64 min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-gray-900">
        {/* Top Bar */}
        <div className="sticky top-0 z-10 bg-gray-900/80 backdrop-blur-sm border-b border-gray-800">
          <div className="px-8 py-4 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-white">
                {navItems.find(item => 
                  location.pathname === item.path || 
                  (item.path !== '/' && location.pathname.startsWith(item.path))
                )?.label || 'Dashboard'}
              </h2>
              <p className="text-sm text-gray-400">
                Real-time security monitoring and vulnerability management
              </p>
            </div>
            
            <div className="flex items-center space-x-4">
              {/* Notifications */}
              <button className="relative p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg">
                <div className="w-2 h-2 bg-red-500 rounded-full absolute top-2 right-2"></div>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                    d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
              </button>
              
              {/* Quick Actions */}
              <button className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors">
                New Scan
              </button>
            </div>
          </div>
        </div>
        
        {/* Page Content */}
        <div className="p-8">
          {children}
        </div>
      </main>
    </div>
  )
}

export default Layout