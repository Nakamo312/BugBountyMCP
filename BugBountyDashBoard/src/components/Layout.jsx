import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import ProgramSelector from './ProgramSelector'
import { ActionQueueStatusToasts } from './notifications/ActionQueueStatusToasts'
import { dashboardNavGroups, isNavItemActive } from '../navigation/dashboardNavigation'

const Layout = ({ children }) => {
  const location = useLocation()

  return (
    <div className="terminal-workbench-shell min-h-screen bg-gray-50">
      <aside className="fixed left-0 top-0 h-full w-72 border-r border-gray-800 bg-gray-950 text-white shadow-lg">
        <div className="flex h-full flex-col">
          <div className="border-b border-gray-800 p-6">
            <div className="mb-3 inline-flex rounded-full border border-cyan-200/40 bg-cyan-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-600">
              terminal ui
            </div>
            <h1 className="terminal-title-prefix text-xl font-bold text-slate-100">Bug Bounty MCP</h1>
            <p className="mt-1 text-xs text-gray-400">scope / graph / runs</p>
          </div>

          <div className="border-b border-gray-800 p-4">
            <ProgramSelector />
          </div>

          <nav className="flex-1 space-y-5 overflow-y-auto p-4">
            {dashboardNavGroups.map((group) => (
              <section key={group.id}>
                <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                  {group.label}
                </div>
                <div className="space-y-1">
                  {group.items.map((item) => {
                    const Icon = item.icon
                    const active = isNavItemActive(item, location.pathname)
                    return (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`group flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors ${
                          active
                            ? 'border-cyan-200 bg-cyan-600 text-white'
                            : 'border-transparent text-gray-300 hover:border-gray-800 hover:bg-gray-800 hover:text-white'
                        }`}
                      >
                        <Icon size={18} />
                        <span className="font-medium">{item.label}</span>
                      </Link>
                    )
                  })}
                </div>
              </section>
            ))}
          </nav>

          <div className="border-t border-gray-800 p-4 text-sm text-gray-400">
            <div className="flex items-center gap-2 font-mono text-xs">
              <AlertCircle size={16} />
              <span>api:v0.1.0</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="ml-72 p-8">
        {children}
      </main>
      <ActionQueueStatusToasts />
    </div>
  )
}

export default Layout
