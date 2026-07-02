import {
  Activity,
  BarChart3,
  Database,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  PlayCircle,
  Search,
  Server,
  ShieldAlert,
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
    id: 'investigate',
    label: 'Investigate',
    items: [
      { path: '/workbench', icon: Workflow, label: 'Workbench', matchPrefix: '/workbench' },
      { path: '/hosts', icon: Server, label: 'Assets' },
      { path: '/analysis', icon: ShieldAlert, label: 'Analysis' },
    ],
  },
  {
    id: 'graph',
    label: 'Graph',
    items: [
      { path: '/graph/components', icon: GitBranch, label: 'Component Analysis', aliases: ['/surface-components'] },
      { path: '/graph/pipeline', icon: BarChart3, label: 'Projection Pipeline' },
    ],
  },
  {
    id: 'execution',
    label: 'Execution',
    items: [
      { path: '/execution', icon: Activity, label: 'Execution', matchPrefix: '/execution', aliases: ['/workspace'] },
      { path: '/actions', icon: PlayCircle, label: 'Action Catalog' },
    ],
  },
  {
    id: 'knowledge',
    label: 'Knowledge',
    items: [
      { path: '/knowledge/evidence', icon: Search, label: 'Evidence' },
      { path: '/knowledge/search', icon: Database, label: 'Search Index' },
    ],
  },
]

export const isNavItemActive = (item, pathname) => {
  if (item.exact) return pathname === item.path
  if (item.matchPrefix && pathname.startsWith(item.matchPrefix)) return true
  if (pathname === item.path) return true
  return (item.aliases || []).some((alias) => pathname === alias || pathname.startsWith(`${alias}/`))
}
