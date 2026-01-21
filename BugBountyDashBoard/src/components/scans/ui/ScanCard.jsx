import clsx from 'clsx'

const colorMap = {
  blue: { bg: 'bg-blue-100', text: 'text-blue-600' },
  green: { bg: 'bg-green-100', text: 'text-green-600' },
  purple: { bg: 'bg-purple-100', text: 'text-purple-600' },
  indigo: { bg: 'bg-indigo-100', text: 'text-indigo-600' },
  red: { bg: 'bg-red-100', text: 'text-red-600' },
  pink: { bg: 'bg-pink-100', text: 'text-pink-600' },
  yellow: { bg: 'bg-yellow-100', text: 'text-yellow-600' },
  orange: { bg: 'bg-orange-100', text: 'text-orange-600' },
  cyan: { bg: 'bg-cyan-100', text: 'text-cyan-600' },
  teal: { bg: 'bg-teal-100', text: 'text-teal-600' },
  rose: { bg: 'bg-rose-100', text: 'text-rose-600' },
  violet: { bg: 'bg-violet-100', text: 'text-violet-600' },
  slate: { bg: 'bg-slate-100', text: 'text-slate-600' },
  amber: { bg: 'bg-amber-100', text: 'text-amber-600' },
}

function ScanCard({ scan, children, active }) {
  const Icon = scan.icon
  const colors = colorMap[scan.color] || { bg: 'bg-gray-100', text: 'text-gray-600' }

  return (
    <div className={clsx(
      'bg-white rounded-lg p-6 border-2 transition-colors',
      active ? 'border-primary-500' : 'border-transparent hover:border-gray-200'
    )}>
      <header className="flex items-center gap-3 mb-4">
        <div className={clsx('p-2 rounded-lg', colors.bg)}>
          <Icon className={colors.text} size={24} />
        </div>
        <div>
          <h3 className="font-semibold text-gray-900">{scan.name}</h3>
          <p className="text-sm text-gray-600">{scan.description}</p>
        </div>
      </header>

      {children}
    </div>
  )
}

export default ScanCard
