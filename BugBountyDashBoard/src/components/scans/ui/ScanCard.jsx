import clsx from 'clsx'

function ScanCard({ scan, children, active }) {
  const Icon = scan.icon

  return (
    <div className={clsx(
      'bg-white rounded-lg p-6 border-2',
      active ? 'border-primary-500' : 'border-transparent'
    )}>
      <header className="flex items-center gap-3 mb-4">
        <Icon />
        <div>
          <h3>{scan.name}</h3>
          <p className="text-sm text-gray-600">{scan.description}</p>
        </div>
      </header>

      {children}
    </div>
  )
}

export default ScanCard