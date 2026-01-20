import React, { useState, useEffect } from 'react'
import { useProgram } from '../context/ProgramContext'
import axios from 'axios'
import {
  getHostsByProgram,
  getHostWithEndpoints,
  getEndpointWithDetails,
  getParametersByEndpoint,
  getHeadersByEndpoint,
} from '../services/api'
import {
  Server, Globe, ChevronRight, ChevronDown, Filter,
  Loader, AlertCircle, ExternalLink, Search, Send, X
} from 'lucide-react'

const Hosts = () => {
  const { selectedProgram } = useProgram()
  const [hosts, setHosts] = useState([])
  const [loading, setLoading] = useState(false)
  const [inScopeFilter, setInScopeFilter] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedHosts, setExpandedHosts] = useState(new Set())
  const [expandedEndpoints, setExpandedEndpoints] = useState(new Set())
  const [endpointDetails, setEndpointDetails] = useState({})
  const [loadingDetails, setLoadingDetails] = useState(new Set())
  const [pagination, setPagination] = useState({ limit: 50, offset: 0, total: 0 })
  const [requestResponses, setRequestResponses] = useState({})
  const [loadingRequests, setLoadingRequests] = useState(new Set())

  useEffect(() => {
    if (selectedProgram) {
      loadHosts()
    }
  }, [selectedProgram, inScopeFilter, pagination.offset, pagination.limit])

  const loadHosts = async () => {
    if (!selectedProgram) return
    
    setLoading(true)
    try {
      const params = {
        limit: pagination.limit,
        offset: pagination.offset,
      }
      if (inScopeFilter !== null) {
        params.in_scope = inScopeFilter
      }
      
      const response = await getHostsByProgram(selectedProgram.id, params)
      setHosts(response.data.hosts || [])
      setPagination(prev => ({
        ...prev,
        total: response.data.total || 0,
      }))
    } catch (error) {
      console.error('Failed to load hosts:', error)
      alert('Failed to load hosts: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const toggleHost = async (hostId) => {
    const newExpanded = new Set(expandedHosts)
    if (newExpanded.has(hostId)) {
      newExpanded.delete(hostId)
    } else {
      newExpanded.add(hostId)
      // Load endpoints if not already loaded
      if (!endpointDetails[hostId]) {
        await loadHostEndpoints(hostId)
      }
    }
    setExpandedHosts(newExpanded)
  }

  const loadHostEndpoints = async (hostId) => {
    try {
      const response = await getHostWithEndpoints(hostId)
      setEndpointDetails(prev => ({
        ...prev,
        [hostId]: response.data.endpoints || [],
      }))
    } catch (error) {
      console.error('Failed to load endpoints:', error)
    }
  }

  const toggleEndpoint = async (endpointId) => {
    const newExpanded = new Set(expandedEndpoints)
    if (newExpanded.has(endpointId)) {
      newExpanded.delete(endpointId)
    } else {
      newExpanded.add(endpointId)
      // Load details if not already loaded
      if (!endpointDetails[endpointId]) {
        await loadEndpointDetails(endpointId)
      }
    }
    setExpandedEndpoints(newExpanded)
  }

  const loadEndpointDetails = async (endpointId) => {
    setLoadingDetails(prev => new Set(prev).add(endpointId))
    try {
      const [detailsResponse, paramsResponse, headersResponse] = await Promise.all([
        getEndpointWithDetails(endpointId),
        getParametersByEndpoint(endpointId),
        getHeadersByEndpoint(endpointId),
      ])
      
      setEndpointDetails(prev => ({
        ...prev,
        [endpointId]: {
          endpoint: detailsResponse.data.endpoint,
          parameters: paramsResponse.data || [],
          headers: headersResponse.data || [],
        },
      }))
    } catch (error) {
      console.error('Failed to load endpoint details:', error)
    } finally {
      setLoadingDetails(prev => {
        const newSet = new Set(prev)
        newSet.delete(endpointId)
        return newSet
      })
    }
  }

  const filteredHosts = hosts.filter(host => {
    if (searchTerm && !host.host.toLowerCase().includes(searchTerm.toLowerCase())) {
      return false
    }
    return true
  })

  const handlePageChange = (newOffset) => {
    setPagination(prev => ({ ...prev, offset: newOffset }))
  }

  const makeRequest = async (endpoint, host) => {
    const endpointId = endpoint.id
    setLoadingRequests(prev => new Set(prev).add(endpointId))
    
    try {
      // Build URL
      const scheme = 'https' // Default to https, could be made configurable
      const baseUrl = `${scheme}://${host.host}`
      const url = `${baseUrl}${endpoint.path}`
      
      // Get method (default to GET if available, otherwise first method)
      const method = endpoint.methods?.includes('GET') ? 'GET' : (endpoint.methods?.[0] || 'GET')
      
      // Get details for parameters and headers
      const details = endpointDetails[endpointId]
      const params = details?.parameters || []
      const headers = details?.headers || []
      
      // Build query params
      const queryParams = {}
      params.forEach(param => {
        if (param.location === 'query' && param.example_value) {
          queryParams[param.name] = param.example_value
        }
      })
      
      // Build request headers
      const requestHeaders = {}
      headers.forEach(header => {
        requestHeaders[header.name] = header.value
      })
      
      // Make the request
      const response = await axios({
        method: method,
        url: url,
        params: Object.keys(queryParams).length > 0 ? queryParams : undefined,
        headers: requestHeaders,
        validateStatus: () => true, // Accept all status codes
        timeout: 10000,
      })
      
      // Store response
      setRequestResponses(prev => ({
        ...prev,
        [endpointId]: {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
          data: response.data,
          url: response.config.url || url,
        }
      }))
    } catch (error) {
      setRequestResponses(prev => ({
        ...prev,
        [endpointId]: {
          error: error.message,
          url: `${scheme}://${host.host}${endpoint.path}`,
        }
      }))
    } finally {
      setLoadingRequests(prev => {
        const newSet = new Set(prev)
        newSet.delete(endpointId)
        return newSet
      })
    }
  }

  const clearResponse = (endpointId) => {
    setRequestResponses(prev => {
      const newState = { ...prev }
      delete newState[endpointId]
      return newState
    })
  }

  if (!selectedProgram) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="flex items-center space-x-3">
          <AlertCircle className="text-yellow-600" size={24} />
          <div>
            <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
            <p className="text-sm text-yellow-700 mt-1">
              Please select a program from the sidebar to view hosts.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Hosts</h1>
        <p className="text-gray-600 mt-2">
          View hosts and endpoints for program: <span className="font-semibold text-primary-600">{selectedProgram.name}</span>
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center space-x-2">
            <Search className="text-gray-400" size={20} />
            <input
              type="text"
              placeholder="Search hosts..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div className="flex items-center space-x-2">
            <Filter className="text-gray-400" size={20} />
            <select
              value={inScopeFilter === null ? 'all' : inScopeFilter.toString()}
              onChange={(e) => {
                const value = e.target.value
                setInScopeFilter(value === 'all' ? null : value === 'true')
              }}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All Hosts</option>
              <option value="true">In Scope Only</option>
              <option value="false">Out of Scope Only</option>
            </select>
          </div>
          <button
            onClick={loadHosts}
            disabled={loading}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? <Loader className="animate-spin" size={16} /> : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Total Hosts</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{pagination.total}</p>
            </div>
            <Server className="text-primary-500" size={32} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">In Scope</p>
              <p className="text-2xl font-bold text-green-600 mt-1">
                {hosts.filter(h => h.in_scope).length}
              </p>
            </div>
            <Globe className="text-green-500" size={32} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Visible</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{filteredHosts.length}</p>
            </div>
            <Search className="text-gray-500" size={32} />
          </div>
        </div>
      </div>

      {/* Hosts List */}
      {loading && filteredHosts.length === 0 ? (
        <div className="flex items-center justify-center h-64">
          <Loader className="animate-spin text-primary-500" size={32} />
        </div>
      ) : filteredHosts.length === 0 ? (
        <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center">
          <Server className="mx-auto text-gray-400" size={48} />
          <h3 className="mt-4 text-lg font-medium text-gray-900">No hosts found</h3>
          <p className="mt-2 text-sm text-gray-600">
            {searchTerm ? 'Try adjusting your search terms' : 'No hosts available for this program'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredHosts.map((host) => {
            const isExpanded = expandedHosts.has(host.id)
            const endpoints = endpointDetails[host.id] || []
            const endpointCount = endpoints.length

            return (
              <div key={host.id} className="bg-white rounded-lg shadow">
                {/* Host Header */}
                <button
                  onClick={() => toggleHost(host.id)}
                  className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left"
                >
                  <div className="flex items-center space-x-4 flex-1 min-w-0">
                    {isExpanded ? (
                      <ChevronDown className="text-gray-400 flex-shrink-0" size={20} />
                    ) : (
                      <ChevronRight className="text-gray-400 flex-shrink-0" size={20} />
                    )}
                    <Server className={`flex-shrink-0 ${host.in_scope ? 'text-green-500' : 'text-gray-400'}`} size={20} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-gray-900 truncate">{host.host}</span>
                        {host.in_scope && (
                          <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800 rounded">
                            In Scope
                          </span>
                        )}
                      </div>
                      {host.cname && host.cname.length > 0 && (
                        <p className="text-sm text-gray-500 truncate mt-1">
                          CNAME: {host.cname.join(', ')}
                        </p>
                      )}
                    </div>
                    {endpointCount > 0 && (
                      <span className="px-3 py-1 text-sm font-medium bg-primary-100 text-primary-800 rounded-full">
                        {endpointCount} endpoint{endpointCount !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </button>

                {/* Endpoints */}
                {isExpanded && endpoints.length > 0 && (
                  <div className="border-t border-gray-200 p-4 space-y-2">
                    {endpoints.map((endpoint) => {
                      const isEndpointExpanded = expandedEndpoints.has(endpoint.id)
                      const details = endpointDetails[endpoint.id]
                      const isLoadingDetails = loadingDetails.has(endpoint.id)

                      return (
                        <div key={endpoint.id} className="border border-gray-200 rounded-lg">
                          <button
                            onClick={() => toggleEndpoint(endpoint.id)}
                            className="w-full flex items-center justify-between p-3 hover:bg-gray-50 transition-colors text-left"
                          >
                            <div className="flex items-center space-x-3 flex-1 min-w-0">
                              {isEndpointExpanded ? (
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
                                        <span
                                          key={idx}
                                          className={`px-2 py-0.5 text-xs font-medium rounded ${
                                            method === 'GET'
                                              ? 'bg-blue-100 text-blue-800'
                                              : method === 'POST'
                                              ? 'bg-green-100 text-green-800'
                                              : method === 'PUT'
                                              ? 'bg-yellow-100 text-yellow-800'
                                              : method === 'DELETE'
                                              ? 'bg-red-100 text-red-800'
                                              : 'bg-gray-100 text-gray-800'
                                          }`}
                                        >
                                          {method}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                  {endpoint.status_code && (
                                    <span
                                      className={`px-2 py-0.5 text-xs font-medium rounded ${
                                        endpoint.status_code >= 200 && endpoint.status_code < 300
                                          ? 'bg-green-100 text-green-800'
                                          : endpoint.status_code >= 400
                                          ? 'bg-red-100 text-red-800'
                                          : 'bg-gray-100 text-gray-800'
                                      }`}
                                    >
                                      {endpoint.status_code}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </button>

                          {/* Endpoint Details */}
                          {isEndpointExpanded && (
                            <div className="border-t border-gray-200 p-4 bg-gray-50 space-y-4">
                              {isLoadingDetails ? (
                                <div className="flex items-center justify-center py-4">
                                  <Loader className="animate-spin text-primary-500" size={20} />
                                </div>
                              ) : details ? (
                                <>
                                  {/* Request Button */}
                                  <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
                                    <div>
                                      <h4 className="font-semibold text-gray-900">Make Request</h4>
                                      <p className="text-sm text-gray-600 mt-1">
                                        Test this endpoint by making an HTTP request
                                      </p>
                                    </div>
                                    <button
                                      onClick={() => makeRequest(endpoint, host)}
                                      disabled={loadingRequests.has(endpoint.id)}
                                      className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                    >
                                      {loadingRequests.has(endpoint.id) ? (
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

                                  {/* Response Display */}
                                  {requestResponses[endpoint.id] && (
                                    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4">
                                      <div className="flex items-center justify-between">
                                        <h4 className="font-semibold text-gray-900">Response</h4>
                                        <button
                                          onClick={() => clearResponse(endpoint.id)}
                                          className="text-gray-400 hover:text-gray-600"
                                        >
                                          <X size={18} />
                                        </button>
                                      </div>
                                      
                                      {requestResponses[endpoint.id].error ? (
                                        <div className="bg-red-50 border border-red-200 rounded p-3">
                                          <p className="text-sm text-red-800 font-medium">Error</p>
                                          <p className="text-sm text-red-600 mt-1">{requestResponses[endpoint.id].error}</p>
                                          <p className="text-xs text-red-500 mt-2 font-mono">{requestResponses[endpoint.id].url}</p>
                                        </div>
                                      ) : (
                                        <>
                                          <div className="flex items-center space-x-4 text-sm">
                                            <div>
                                              <span className="text-gray-600">Status: </span>
                                              <span className={`font-semibold ${
                                                requestResponses[endpoint.id].status >= 200 && requestResponses[endpoint.id].status < 300
                                                  ? 'text-green-600'
                                                  : requestResponses[endpoint.id].status >= 400
                                                  ? 'text-red-600'
                                                  : 'text-gray-600'
                                              }`}>
                                                {requestResponses[endpoint.id].status} {requestResponses[endpoint.id].statusText}
                                              </span>
                                            </div>
                                            <div>
                                              <span className="text-gray-600">URL: </span>
                                              <span className="font-mono text-xs text-gray-800">{requestResponses[endpoint.id].url}</span>
                                            </div>
                                          </div>
                                          
                                          {/* Response Headers */}
                                          {requestResponses[endpoint.id].headers && (
                                            <div>
                                              <h5 className="text-sm font-semibold text-gray-700 mb-2">Response Headers</h5>
                                              <div className="bg-gray-50 border border-gray-200 rounded p-3 space-y-1 max-h-32 overflow-y-auto">
                                                {Object.entries(requestResponses[endpoint.id].headers).map(([key, value]) => (
                                                  <div key={key} className="flex items-start space-x-2 text-xs">
                                                    <span className="font-medium text-gray-700 min-w-[150px]">{key}:</span>
                                                    <span className="text-gray-600 font-mono break-all">{String(value)}</span>
                                                  </div>
                                                ))}
                                              </div>
                                            </div>
                                          )}
                                          
                                          {/* Response Body in iframe */}
                                          <div>
                                            <h5 className="text-sm font-semibold text-gray-700 mb-2">Response Body</h5>
                                            <div className="border border-gray-200 rounded overflow-hidden">
                                              <iframe
                                                srcDoc={`
                                                  <!DOCTYPE html>
                                                  <html>
                                                    <head>
                                                      <meta charset="utf-8">
                                                      <style>
                                                        body {
                                                          margin: 0;
                                                          padding: 16px;
                                                          font-family: monospace;
                                                          font-size: 12px;
                                                          background: #fff;
                                                          color: #000;
                                                        }
                                                        pre {
                                                          margin: 0;
                                                          white-space: pre-wrap;
                                                          word-wrap: break-word;
                                                        }
                                                      </style>
                                                    </head>
                                                    <body>
                                                      <pre>${typeof requestResponses[endpoint.id].data === 'object' 
                                                        ? JSON.stringify(requestResponses[endpoint.id].data, null, 2)
                                                        : String(requestResponses[endpoint.id].data || '')
                                                      }</pre>
                                                    </body>
                                                  </html>
                                                `}
                                                className="w-full h-64 border-0"
                                                title="Response Body"
                                              />
                                            </div>
                                          </div>
                                        </>
                                      )}
                                    </div>
                                  )}

                                  {/* Parameters */}
                                  {details.parameters && details.parameters.length > 0 && (
                                    <div>
                                      <h4 className="font-semibold text-gray-900 mb-2">Parameters ({details.parameters.length})</h4>
                                      <div className="space-y-2">
                                        {details.parameters.map((param) => (
                                          <div
                                            key={param.id}
                                            className="bg-white border border-gray-200 rounded p-3"
                                          >
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
                                                  <span className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded">
                                                    Reflected
                                                  </span>
                                                )}
                                                {param.is_array && (
                                                  <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-800 rounded">
                                                    Array
                                                  </span>
                                                )}
                                              </div>
                                            </div>
                                            {param.example_value && (
                                              <p className="text-xs text-gray-600 mt-1 font-mono">
                                                Example: {param.example_value}
                                              </p>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {/* Headers */}
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
                                </>
                              ) : (
                                <div className="text-center py-4">
                                  <button
                                    onClick={() => loadEndpointDetails(endpoint.id)}
                                    className="text-primary-600 hover:text-primary-700 text-sm font-medium"
                                  >
                                    Load Details
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

                {isExpanded && endpoints.length === 0 && (
                  <div className="border-t border-gray-200 p-4 text-center text-sm text-gray-500">
                    No endpoints found for this host
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      {pagination.total > pagination.limit && (
        <div className="flex items-center justify-between bg-white rounded-lg shadow p-4">
          <div className="text-sm text-gray-600">
            Showing {pagination.offset + 1} to {Math.min(pagination.offset + pagination.limit, pagination.total)} of {pagination.total} hosts
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => handlePageChange(Math.max(0, pagination.offset - pagination.limit))}
              disabled={pagination.offset === 0}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              onClick={() => handlePageChange(pagination.offset + pagination.limit)}
              disabled={pagination.offset + pagination.limit >= pagination.total}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default Hosts
