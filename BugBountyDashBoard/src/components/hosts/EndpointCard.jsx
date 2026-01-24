import { ChevronRight, ChevronDown, Globe } from 'lucide-react'
import { MethodBadge } from './EndpointDetails'

const StatusBadge = ({ statusCode }) => {
  if (!statusCode) return null

  const color =
    statusCode >= 200 && statusCode < 300
      ? 'bg-green-100 text-green-800'
      : statusCode >= 400
      ? 'bg-red-100 text-red-800'
      : 'bg-gray-100 text-gray-800'

  return <span className={`px-2 py-0.5 text-xs font-medium rounded ${color}`}>{statusCode}</span>
}

const EndpointCard = ({ endpoint, isExpanded, onToggle, children }) => {
  return (
    <div className="border border-gray-200 rounded-lg">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3 hover:bg-gray-50 transition-colors text-left"
      >
        <div className="flex items-center space-x-3 flex-1 min-w-0">
          {isExpanded ? (
            <ChevronDown className="text-gray-400 flex-shrink-0" size={18} />
          ) : (
            <ChevronRight className="text-gray-400 flex-shrink-0" size={18} />
          )}
          <Globe className="text-blue-500 flex-shrink-0" size={18} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 flex-wrap">
              <span className="font-mono text-sm text-gray-900 truncate">{endpoint.path}</span>
              {endpoint.methods && endpoint.methods.length > 0 && (
                <div className="flex space-x-1">
                  {endpoint.methods.map((method, idx) => (
                    <MethodBadge key={idx} method={method} />
                  ))}
                </div>
              )}
              <StatusBadge statusCode={endpoint.status_code} />
            </div>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-gray-200 p-4 bg-gray-50">{children}</div>
      )}
    </div>
  )
}

export default EndpointCard
