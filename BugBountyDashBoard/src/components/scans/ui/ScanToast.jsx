import { CheckCircle, XCircle } from 'lucide-react'
import { useEffect } from 'react'

export default function ScanToast({ scanResult, onClose, duration = 5000 }) {
  useEffect(() => {
    if (scanResult) {
      const timer = setTimeout(onClose, duration)
      return () => clearTimeout(timer)
    }
  }, [scanResult, onClose, duration])

  if (!scanResult) return null

  const isSuccess = scanResult.status === 'success'

  return (
    <div className="fixed top-5 right-5 w-96 z-50">
      <div className={`flex items-start space-x-3 p-4 rounded-lg shadow-lg border ${
        isSuccess ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
      }`}>
        {isSuccess ? (
          <CheckCircle className="text-green-600 mt-0.5" size={20} />
        ) : (
          <XCircle className="text-red-600 mt-0.5" size={20} />
        )}
        <div className="flex-1">
          <p className={`font-medium ${isSuccess ? 'text-green-900' : 'text-red-900'}`}>
            {scanResult.message || (isSuccess ? 'Scan completed successfully' : 'Scan failed')}
          </p>
          {scanResult.results && (
            <pre className="mt-2 text-xs text-gray-700 bg-white p-2 rounded overflow-x-auto">
              {JSON.stringify(scanResult.results, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}
