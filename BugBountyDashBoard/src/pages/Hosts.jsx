import { useState } from 'react'
import { useProgram } from '../context/ProgramContext'
import { Server, Loader, AlertCircle } from 'lucide-react'
import useHosts from '../hooks/useHosts'
import { proxyRequest } from '../services/api'
import {
  HostCard,
  HostFilters,
  HostStats,
  EndpointCard,
  EndpointDetails,
  Pagination,
} from '../components/hosts'

const Hosts = () => {
  const { selectedProgram } = useProgram()
  const {
    hosts,
    allHosts,
    programStats,
    loading,
    inScopeFilter,
    setInScopeFilter,
    searchTerm,
    setSearchTerm,
    expandedHosts,
    expandedEndpoints,
    endpointDetails,
    loadingDetails,
    pagination,
    toggleHost,
    toggleEndpoint,
    loadEndpointDetails,
    handlePageChange,
    refresh,
  } = useHosts(selectedProgram)

  const [requestResponses, setRequestResponses] = useState({})
  const [loadingRequests, setLoadingRequests] = useState(new Set())

  const makeRequest = async (endpoint, host) => {
    const endpointId = endpoint.id
    setLoadingRequests(prev => new Set(prev).add(endpointId))

    try {
      const scheme = 'https'
      const baseUrl = `${scheme}://${host.host}`
      let url = `${baseUrl}${endpoint.path}`
      const method = endpoint.methods?.includes('GET') ? 'GET' : (endpoint.methods?.[0] || 'GET')

      const details = endpointDetails[endpointId]
      const params = details?.parameters || []
      const headers = details?.headers || []

      const queryParams = {}
      params.forEach(param => {
        if (param.location === 'query' && param.example_value) {
          queryParams[param.name] = param.example_value
        }
      })

      const requestHeaders = {}
      headers.forEach(header => {
        requestHeaders[header.name] = header.value
      })

      if (Object.keys(queryParams).length > 0) {
        const searchParams = new URLSearchParams(queryParams)
        url = `${url}?${searchParams.toString()}`
      }

      const response = await proxyRequest({
        url,
        method,
        headers: Object.keys(requestHeaders).length > 0 ? requestHeaders : null,
        timeout: 10,
      })

      setRequestResponses(prev => ({
        ...prev,
        [endpointId]: {
          status: response.data.status_code,
          statusText: response.data.status_text,
          headers: response.data.headers,
          data: response.data.body,
          url: response.data.url,
        },
      }))
    } catch (error) {
      setRequestResponses(prev => ({
        ...prev,
        [endpointId]: {
          error: error.response?.data?.detail || error.message,
          url: `https://${host.host}${endpoint.path}`,
        },
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
          View hosts and endpoints for program:{' '}
          <span className="font-semibold text-primary-600">{selectedProgram.name}</span>
        </p>
      </div>

      <HostFilters
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        inScopeFilter={inScopeFilter}
        onFilterChange={setInScopeFilter}
        onRefresh={refresh}
        loading={loading}
      />

      <HostStats programStats={programStats} hosts={allHosts} filteredCount={hosts.length} />

      {loading && hosts.length === 0 ? (
        <div className="flex items-center justify-center h-64">
          <Loader className="animate-spin text-primary-500" size={32} />
        </div>
      ) : hosts.length === 0 ? (
        <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center">
          <Server className="mx-auto text-gray-400" size={48} />
          <h3 className="mt-4 text-lg font-medium text-gray-900">No hosts found</h3>
          <p className="mt-2 text-sm text-gray-600">
            {searchTerm ? 'Try adjusting your search terms' : 'No hosts available for this program'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {hosts.map((host) => {
            const isExpanded = expandedHosts.has(host.id)
            const endpoints = endpointDetails[host.id] || []

            return (
              <HostCard
                key={host.id}
                host={host}
                isExpanded={isExpanded}
                onToggle={() => toggleHost(host.id)}
              >
                {isExpanded && endpoints.length > 0 && (
                  <div className="border-t border-gray-200 p-4 space-y-2">
                    {endpoints.map((endpoint) => {
                      const isEndpointExpanded = expandedEndpoints.has(endpoint.id)
                      const details = endpointDetails[endpoint.id]
                      const isLoadingDetails = loadingDetails.has(endpoint.id)

                      return (
                        <EndpointCard
                          key={endpoint.id}
                          endpoint={endpoint}
                          isExpanded={isEndpointExpanded}
                          onToggle={() => toggleEndpoint(endpoint.id)}
                        >
                          <EndpointDetails
                            endpoint={endpoint}
                            host={host}
                            details={details}
                            isLoading={isLoadingDetails}
                            response={requestResponses[endpoint.id]}
                            isRequestLoading={loadingRequests.has(endpoint.id)}
                            onMakeRequest={makeRequest}
                            onClearResponse={() => clearResponse(endpoint.id)}
                            onLoadDetails={loadEndpointDetails}
                          />
                        </EndpointCard>
                      )
                    })}
                  </div>
                )}

                {isExpanded && endpoints.length === 0 && (
                  <div className="border-t border-gray-200 p-4 text-center text-sm text-gray-500">
                    No endpoints found for this host
                  </div>
                )}
              </HostCard>
            )
          })}
        </div>
      )}

      <Pagination pagination={pagination} onPageChange={handlePageChange} />
    </div>
  )
}

export default Hosts
