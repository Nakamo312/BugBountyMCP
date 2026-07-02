import {
  Activity,
  FolderKanban,
  LayoutDashboard,
  PlayCircle,
  Workflow,
} from 'lucide-react'

export const dashboardNavGroups = [
  {
    id: 'program',
    label: 'Program',
    items: [
      { path: '/', icon: LayoutDashboard, label: 'Program Overview', exact: true },
      { path: '/programs', icon: FolderKanban, label: 'Programs' },
    ],
  },
  {
    id: 'operate',
    label: 'Operate',
    items: [
      { path: '/workbench', icon: Workflow, label: 'Workbench', matchPrefix: '/workbench' },
      { path: '/execution', icon: Activity, label: 'Execution', matchPrefix: '/execution', aliases: ['/workspace'] },
      { path: '/actions', icon: PlayCircle, label: 'Action Catalog' },
    ],
  },
]

export const isNavItemActive = (item, pathname) => {
  if (item.exact) return pathname === item.path
  if (item.matchPrefix && pathname.startsWith(item.matchPrefix)) return true
  if (pathname === item.path) return true
  return (item.aliases || []).some((alias) => pathname === alias || pathname.startsWith(`${alias}/`))
}
