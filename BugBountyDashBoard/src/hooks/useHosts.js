import { useState, useEffect, useCallback } from 'react'
import {
  getHostsWithStats,
  getHostWithEndpoints,
  getEndpointWithDetails,
  getParametersByEndpoint,
  getHeadersByEndpoint,
  getProgramStats,
} from '../services/api'

export const useHosts = (selectedProgram) => {
  const [hosts, setHosts] = useState([])
  const [programStats, setProgramStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [inScopeFilter, setInScopeFilter] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedHosts, setExpandedHosts] = useState(new Set())
  const [expandedEndpoints, setExpandedEndpoints] = useState(new Set())
  const [endpointDetails, setEndpointDetails] = useState({})
  const [loadingDetails, setLoadingDetails] = useState(new Set())
  const [pagination, setPagination] = useState({ limit: 50, offset: 0, total: 0 })

  const loadHosts = useCallback(async () => {
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

      const response = await getHostsWithStats(selectedProgram.id, params)
      setHosts(response.data.hosts || [])
      setPagination(prev => ({
        ...prev,
        total: response.data.total || 0,
      }))
    } catch (error) {
      console.error('Failed to load hosts:', error)
      throw error
    } finally {
      setLoading(false)
    }
  }, [selectedProgram, inScopeFilter, pagination.limit, pagination.offset])

  const loadProgramStats = useCallback(async () => {
    if (!selectedProgram) return

    try {
      const response = await getProgramStats(selectedProgram.id)
      setProgramStats(response.data)
    } catch (error) {
      console.error('Failed to load program stats:', error)
    }
  }, [selectedProgram])

  useEffect(() => {
    if (selectedProgram) {
      loadHosts()
      loadProgramStats()
    }
  }, [selectedProgram, loadHosts, loadProgramStats])

  const toggleHost = useCallback(async (hostId) => {
    const newExpanded = new Set(expandedHosts)
    if (newExpanded.has(hostId)) {
      newExpanded.delete(hostId)
    } else {
      newExpanded.add(hostId)
      if (!endpointDetails[hostId]) {
        await loadHostEndpoints(hostId)
      }
    }
    setExpandedHosts(newExpanded)
  }, [expandedHosts, endpointDetails])

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

  const toggleEndpoint = useCallback(async (endpointId) => {
    const newExpanded = new Set(expandedEndpoints)
    if (newExpanded.has(endpointId)) {
      newExpanded.delete(endpointId)
    } else {
      newExpanded.add(endpointId)
      if (!endpointDetails[endpointId]) {
        await loadEndpointDetails(endpointId)
      }
    }
    setExpandedEndpoints(newExpanded)
  }, [expandedEndpoints, endpointDetails])

  const loadEndpointDetails = async (endpointId) => {
    setLoadingDetails(prev => new Set(prev).add(endpointId))
    try {
      const detailsResponse = await getEndpointWithDetails(endpointId)
      let parameters = detailsResponse.data.parameters || []
      let headers = detailsResponse.data.headers || []

      if (parameters.length === 0) {
        try {
          const paramsResponse = await getParametersByEndpoint(endpointId)
          parameters = paramsResponse.data || []
        } catch (e) {
          console.error('Failed to load parameters:', e)
        }
      }

      if (headers.length === 0) {
        try {
          const headersResponse = await getHeadersByEndpoint(endpointId)
          headers = headersResponse.data || []
        } catch (e) {
          console.error('Failed to load headers:', e)
        }
      }

      setEndpointDetails(prev => ({
        ...prev,
        [endpointId]: {
          endpoint: detailsResponse.data.endpoint,
          parameters,
          headers,
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
    const hostName = host.host || ''
    if (searchTerm && !hostName.toLowerCase().includes(searchTerm.toLowerCase())) {
      return false
    }
    return true
  })

  const handlePageChange = (newOffset) => {
    setPagination(prev => ({ ...prev, offset: newOffset }))
  }

  return {
    hosts: filteredHosts,
    allHosts: hosts,
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
    refresh: loadHosts,
  }
}

export default useHosts
