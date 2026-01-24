import { ExternalLink, Copy, Loader } from 'lucide-react'

const MethodBadge = ({ method }) => {
  const colors = {
    GET: 'bg-blue-100 text-blue-800',
    POST: 'bg-green-100 text-green-800',
    PUT: 'bg-yellow-100 text-yellow-800',
    DELETE: 'bg-red-100 text-red-800',
    PATCH: 'bg-purple-100 text-purple-800',
  }
  return (
    <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${colors[method] || 'bg-gray-100'}`}>
      {method}
    </span>
  )
}

const copyToClipboard = (text) => {
  navigator.clipboard.writeText(text)
}

const InjectionRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm">
      <div className="flex items-center space-x-2">
        <span className="font-mono text-xs truncate max-w-xs" title={item.full_url}>
          {item.full_url}
        </span>
        <button onClick={() => copyToClipboard(item.full_url)} className="text-gray-400 hover:text-gray-600">
          <Copy size={14} />
        </button>
      </div>
    </td>
    <td className="px-4 py-3 text-sm">
      <div className="flex gap-1">
        {item.methods?.map((m, i) => <MethodBadge key={i} method={m} />)}
      </div>
    </td>
    <td className="px-4 py-3 text-sm text-center">{item.query_params || 0}</td>
    <td className="px-4 py-3 text-sm text-center">{item.body_params || 0}</td>
    <td className="px-4 py-3 text-sm text-center">{item.path_params || 0}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-1">
        {item.injectable_params?.slice(0, 3).map((p, i) => (
          <span key={i} className="px-1.5 py-0.5 text-xs bg-red-100 text-red-800 rounded">{p}</span>
        ))}
        {item.injectable_params?.length > 3 && (
          <span className="text-xs text-gray-500">+{item.injectable_params.length - 3}</span>
        )}
      </div>
    </td>
  </tr>
)

const SSRFRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm font-mono text-xs truncate max-w-xs">{item.full_url}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex gap-1">
        {item.methods?.map((m, i) => <MethodBadge key={i} method={m} />)}
      </div>
    </td>
    <td className="px-4 py-3 text-sm font-medium">{item.param_name}</td>
    <td className="px-4 py-3 text-sm">
      <span className="px-2 py-0.5 text-xs bg-orange-100 text-orange-800 rounded">{item.location}</span>
    </td>
    <td className="px-4 py-3 text-sm text-gray-500 font-mono text-xs truncate max-w-xs">{item.example_value}</td>
  </tr>
)

const IDORRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm font-mono text-xs truncate max-w-xs">{item.full_url}</td>
    <td className="px-4 py-3 text-sm font-mono text-xs text-gray-500">{item.normalized_path}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex gap-1">
        {item.methods?.map((m, i) => <MethodBadge key={i} method={m} />)}
      </div>
    </td>
    <td className="px-4 py-3 text-sm text-center">{item.param_count}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-1">
        {item.parameters?.slice(0, 3).map((p, i) => (
          <span key={i} className="px-1.5 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded">{p}</span>
        ))}
      </div>
    </td>
  </tr>
)

const ReflectedRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm font-mono text-xs truncate max-w-xs">{item.full_url}</td>
    <td className="px-4 py-3 text-sm font-medium">{item.param_name}</td>
    <td className="px-4 py-3 text-sm">
      <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded">{item.param_location}</span>
    </td>
    <td className="px-4 py-3 text-sm">{item.param_type}</td>
    <td className="px-4 py-3 text-sm text-gray-500 font-mono text-xs">{item.example_value}</td>
    <td className="px-4 py-3 text-sm text-center">
      {item.is_array && <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-800 rounded">Array</span>}
    </td>
  </tr>
)

const AdminDebugRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm">{item.host}</td>
    <td className="px-4 py-3 text-sm font-mono text-xs">{item.path}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex gap-1">
        {item.methods?.map((m, i) => <MethodBadge key={i} method={m} />)}
      </div>
    </td>
    <td className="px-4 py-3 text-sm">
      {item.status_code && (
        <span className={`px-2 py-0.5 text-xs rounded ${
          item.status_code < 400 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
        }`}>
          {item.status_code}
        </span>
      )}
    </td>
  </tr>
)

const TechnologyRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm">{item.host}</td>
    <td className="px-4 py-3 text-sm">{item.address}</td>
    <td className="px-4 py-3 text-sm">{item.scheme}:{item.port}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-1">
        {item.technologies && Object.entries(item.technologies).map(([tech, ver], i) => (
          <span key={i} className="px-1.5 py-0.5 text-xs bg-indigo-100 text-indigo-800 rounded">
            {tech}{ver && typeof ver === 'string' ? `:${ver}` : ''}
          </span>
        ))}
      </div>
    </td>
    <td className="px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-1">
        {item.server_headers?.map((h, i) => (
          <span key={i} className="px-1.5 py-0.5 text-xs bg-gray-100 text-gray-800 rounded">{h}</span>
        ))}
      </div>
    </td>
  </tr>
)

const APIPatternRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm font-mono text-xs">{item.normalized_path}</td>
    <td className="px-4 py-3 text-sm text-center">{item.host_count}</td>
    <td className="px-4 py-3 text-sm text-center">{item.endpoint_count}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex gap-1">
        {item.all_methods?.map((m, i) => <MethodBadge key={i} method={m} />)}
      </div>
    </td>
    <td className="px-4 py-3 text-sm text-center">{item.unique_params}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-1">
        {item.param_names?.slice(0, 3).map((p, i) => (
          <span key={i} className="px-1.5 py-0.5 text-xs bg-cyan-100 text-cyan-800 rounded">{p}</span>
        ))}
      </div>
    </td>
  </tr>
)

const GenericRow = ({ item }) => (
  <tr className="hover:bg-gray-50">
    <td className="px-4 py-3 text-sm">{item.host}</td>
    <td className="px-4 py-3 text-sm font-mono text-xs truncate max-w-md">{item.full_url || item.path}</td>
    <td className="px-4 py-3 text-sm">
      <div className="flex gap-1">
        {item.methods?.map((m, i) => <MethodBadge key={i} method={m} />)}
      </div>
    </td>
    <td className="px-4 py-3 text-sm text-gray-500">
      {item.status_code && <span className="px-2 py-0.5 text-xs bg-gray-100 rounded">{item.status_code}</span>}
    </td>
  </tr>
)

const TABLE_CONFIGS = {
  injection: {
    headers: ['URL', 'Methods', 'Query', 'Body', 'Path', 'Injectable'],
    Row: InjectionRow,
  },
  ssrf: {
    headers: ['URL', 'Methods', 'Parameter', 'Location', 'Example'],
    Row: SSRFRow,
  },
  idor: {
    headers: ['URL', 'Normalized', 'Methods', 'Params', 'Parameters'],
    Row: IDORRow,
  },
  reflected: {
    headers: ['URL', 'Parameter', 'Location', 'Type', 'Example', 'Array'],
    Row: ReflectedRow,
  },
  adminDebug: {
    headers: ['Host', 'Path', 'Methods', 'Status'],
    Row: AdminDebugRow,
  },
  technologies: {
    headers: ['Host', 'IP', 'Service', 'Technologies', 'Server'],
    Row: TechnologyRow,
  },
  apiPatterns: {
    headers: ['Pattern', 'Hosts', 'Endpoints', 'Methods', 'Params', 'Param Names'],
    Row: APIPatternRow,
  },
}

const AnalysisTable = ({ category, data, loading, pagination, onPageChange }) => {
  const config = TABLE_CONFIGS[category] || {
    headers: ['Host', 'URL', 'Methods', 'Status'],
    Row: GenericRow,
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader className="animate-spin text-primary-500" size={32} />
      </div>
    )
  }

  if (!data || !data.items || data.items.length === 0) {
    return (
      <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center">
        <p className="text-gray-500">No results found</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                {config.headers.map((header, i) => (
                  <th
                    key={i}
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {data.items.map((item, i) => (
                <config.Row key={i} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {data.total > pagination.limit && (
        <div className="flex items-center justify-between bg-white rounded-lg shadow p-4">
          <div className="text-sm text-gray-600">
            Showing {pagination.offset + 1} to {Math.min(pagination.offset + pagination.limit, data.total)} of {data.total}
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => onPageChange(Math.max(0, pagination.offset - pagination.limit))}
              disabled={pagination.offset === 0}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={() => onPageChange(pagination.offset + pagination.limit)}
              disabled={pagination.offset + pagination.limit >= data.total}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default AnalysisTable
