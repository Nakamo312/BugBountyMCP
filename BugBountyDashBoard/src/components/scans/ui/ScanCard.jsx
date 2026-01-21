import { useState } from 'react'
import clsx from 'clsx'
import ScanFormFactory from './ScanFormFactory'
import ScanToast from './ScanToast'

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

function ScanCard({ scan, scanRunner }) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [toastResult, setToastResult] = useState(null)

  const handleRunScan = async (data) => {
    const result = await scanRunner.runScan(scan, data)
    if (result) setToastResult(result)
    setIsModalOpen(false) 
  }

  const Icon = scan.icon
  const colors = colorMap[scan.color] || { bg: 'bg-gray-100', text: 'text-gray-600' }

  return (
    <>
      {/* Карточка сканера */}
      <div
        className={clsx(
          'bg-white rounded-lg p-6 border-2 transition-colors cursor-pointer hover:shadow-lg',
          'border-transparent hover:border-gray-200'
        )}
        onClick={() => setIsModalOpen(true)}
      >
        <header className="flex items-center gap-3 mb-4">
          <div className={clsx('p-2 rounded-lg', colors.bg)}>
            <Icon className={colors.text} size={24} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{scan.name}</h3>
            <p className="text-sm text-gray-600">{scan.description}</p>
          </div>
        </header>
      </div>

      {/* Модальное окно с формой */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md relative">
            <button
              className="absolute top-2 right-2 text-gray-400 hover:text-gray-700"
              onClick={() => setIsModalOpen(false)}
            >
              ✕
            </button>
            <h2 className="text-xl font-bold mb-4">{scan.name}</h2>
            <ScanFormFactory
              type={scan.form}
              onScan={handleRunScan}
              loading={scanRunner.loading}
            />
          </div>
        </div>
      )}

      {/* Toast результата */}
      <ScanToast scanResult={toastResult} onClose={() => setToastResult(null)} />
    </>
  )
}

export default ScanCard
