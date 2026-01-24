import { Loader, Send } from 'lucide-react'
import RequestResponse from './RequestResponse'

const MethodBadge = ({ method }) => {
  const colors = {
    GET: 'bg-blue-100 text-blue-800',
    POST: 'bg-green-100 text-green-800',
    PUT: 'bg-yellow-100 text-yellow-800',
    DELETE: 'bg-red-100 text-red-800',
    PATCH: 'bg-purple-100 text-purple-800',
  }

  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded ${colors[method] || 'bg-gray-100 text-gray-800'}`}>
      {method}
    </span>
  )
}

const ParameterCard = ({ param }) => (
  <div className="bg-white border border-gray-200 rounded p-3">
    <div className="flex items-center justify-between mb-1">
      <span className="font-mono text-sm font-medium text-gray-900">{param.name}</span>
      <div className="flex items-center space-x-2">
        <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded">
          {param.location}
        </span>
        <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-800 rounded">
          {param.param_type}
        </span>
        {param.reflected && (
          <span className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded">Reflected</span>
        )}
        {param.is_array && (
          <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-800 rounded">Array</span>
        )}
      </div>
    </div>
    {param.example_value && (
      <p className="text-xs text-gray-600 mt-1 font-mono">Example: {param.example_value}</p>
    )}
  </div>
)

const EndpointDetails = ({
  endpoint,
  host,
  details,
  isLoading,
  response,
  isRequestLoading,
  onMakeRequest,
  onClearResponse,
  onLoadDetails,
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader className="animate-spin text-primary-500" size={20} />
      </div>
    )
  }

  if (!details) {
    return (
      <div className="text-center py-4">
        <button
          onClick={() => onLoadDetails(endpoint.id)}
          className="text-primary-600 hover:text-primary-700 text-sm font-medium"
        >
          Load Details
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
        <div>
          <h4 className="font-semibold text-gray-900">Make Request</h4>
          <p className="text-sm text-gray-600 mt-1">Test this endpoint by making an HTTP request</p>
        </div>
        <button
          onClick={() => onMakeRequest(endpoint, host)}
          disabled={isRequestLoading}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isRequestLoading ? (
            <>
              <Loader className="animate-spin" size={16} />
              <span>Sending...</span>
            </>
          ) : (
            <>
              <Send size={16} />
              <span>Send Request</span>
            </>
          )}
        </button>
      </div>

      <RequestResponse response={response} onClear={onClearResponse} />

      {details.parameters && details.parameters.length > 0 && (
        <div>
          <h4 className="font-semibold text-gray-900 mb-2">
            Parameters ({details.parameters.length})
          </h4>
          <div className="space-y-2">
            {details.parameters.map((param) => (
              <ParameterCard key={param.id} param={param} />
            ))}
          </div>
        </div>
      )}

      {details.headers && details.headers.length > 0 && (
        <div>
          <h4 className="font-semibold text-gray-900 mb-2">Headers ({details.headers.length})</h4>
          <div className="bg-white border border-gray-200 rounded p-3 space-y-1">
            {details.headers.map((header) => (
              <div key={header.id} className="flex items-center space-x-2 text-sm">
                <span className="font-medium text-gray-700">{header.name}:</span>
                <span className="text-gray-600 font-mono">{header.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(!details.parameters || details.parameters.length === 0) &&
        (!details.headers || details.headers.length === 0) && (
          <p className="text-sm text-gray-500 text-center py-4">No additional details available</p>
        )}
    </div>
  )
}

export { MethodBadge }
export default EndpointDetails
