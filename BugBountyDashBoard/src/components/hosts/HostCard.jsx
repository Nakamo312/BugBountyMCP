import { ChevronRight, ChevronDown, Server } from 'lucide-react'

const HostCard = ({ host, isExpanded, onToggle, children }) => {
  return (
    <div className="bg-white rounded-lg shadow">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left"
      >
        <div className="flex items-center space-x-4 flex-1 min-w-0">
          {isExpanded ? (
            <ChevronDown className="text-gray-400 flex-shrink-0" size={20} />
          ) : (
            <ChevronRight className="text-gray-400 flex-shrink-0" size={20} />
          )}
          <Server
            className={`flex-shrink-0 ${host.in_scope ? 'text-green-500' : 'text-gray-400'}`}
            size={20}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 flex-wrap">
              <span className="font-semibold text-gray-900 truncate">{host.host}</span>
              {host.in_scope && (
                <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800 rounded">
                  In Scope
                </span>
              )}
            </div>
            {host.cname && host.cname.length > 0 && (
              <p className="text-sm text-gray-500 truncate mt-1">CNAME: {host.cname.join(', ')}</p>
            )}
            {host.services && host.services.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {host.services.map((service, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-0.5 text-xs bg-blue-50 text-blue-700 rounded"
                  >
                    {service}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center space-x-2">
            {host.endpoint_count > 0 && (
              <span className="px-3 py-1 text-sm font-medium bg-primary-100 text-primary-800 rounded-full">
                {host.endpoint_count} endpoints
              </span>
            )}
            {host.parameter_count > 0 && (
              <span className="px-2 py-1 text-xs bg-purple-100 text-purple-800 rounded">
                {host.parameter_count} params
              </span>
            )}
          </div>
        </div>
      </button>

      {isExpanded && children}
    </div>
  )
}

export default HostCard
