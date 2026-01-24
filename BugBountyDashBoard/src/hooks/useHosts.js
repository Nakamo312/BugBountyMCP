import { useState, useEffect, useCallback, useMemo } from 'react'
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
  const [serviceFilter, setServiceFilter] = useState(null)
  const [techFilter, setTechFilter] = useState(null)
  const [sortBy, setSortBy] = useState('host')
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
      const hostsData = (response.data.hosts || []).map(h => ({
        ...h,
        id: h.host_id || h.id,
      }))
      setHosts(hostsData)
      setPagination(prev => ({
        ...prev,
        total: response.data.total || 0,
      }))
    } catch (error) {
      console.error('Failed to load hosts:', error)
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
    }
  }, [selectedProgram, inScopeFilter, pagination.offset, pagination.limit])

  useEffect(() => {
    if (selectedProgram) {
      loadProgramStats()
    }
  }, [selectedProgram])

  const availableServices = useMemo(() => {
    const servicesSet = new Set()
    hosts.forEach(host => {
      if (host.services) {
        host.services.forEach(s => servicesSet.add(s))
      }
    })
    return Array.from(servicesSet).sort()
  }, [hosts])

  const availableTechs = useMemo(() => {
    const techsSet = new Set()
    hosts.forEach(host => {
      if (host.technologies) {
        Object.keys(host.technologies).forEach(t => techsSet.add(t))
      }
    })
    return Array.from(techsSet).sort()
  }, [hosts])

  const filteredAndSortedHosts = useMemo(() => {
    let result = hosts.filter(host => {
      const hostName = host.host || ''
      if (searchTerm && !hostName.toLowerCase().includes(searchTerm.toLowerCase())) {
        return false
      }
      if (serviceFilter && (!host.services || !host.services.includes(serviceFilter))) {
        return false
      }
      if (techFilter && (!host.technologies || !Object.keys(host.technologies).includes(techFilter))) {
        return false
      }
      return true
    })

    const desc = sortBy.startsWith('-')
    const field = desc ? sortBy.slice(1) : sortBy

    result.sort((a, b) => {
      let aVal = a[field]
      let bVal = b[field]

      if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase()
        bVal = (bVal || '').toLowerCase()
      }

      if (aVal < bVal) return desc ? 1 : -1
      if (aVal > bVal) return desc ? -1 : 1
      return 0
    })

    return result
  }, [hosts, searchTerm, serviceFilter, techFilter, sortBy])

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

  const handlePageChange = (newOffset) => {
    setPagination(prev => ({ ...prev, offset: newOffset }))
  }

  const clearFilters = () => {
    setSearchTerm('')
    setInScopeFilter(null)
    setServiceFilter(null)
    setTechFilter(null)
    setSortBy('host')
  }

  return {
    hosts: filteredAndSortedHosts,
    allHosts: hosts,
    programStats,
    loading,
    inScopeFilter,
    setInScopeFilter,
    serviceFilter,
    setServiceFilter,
    techFilter,
    setTechFilter,
    sortBy,
    setSortBy,
    searchTerm,
    setSearchTerm,
    availableServices,
    availableTechs,
    expandedHosts,
    expandedEndpoints,
    endpointDetails,
    loadingDetails,
    pagination,
    toggleHost,
    toggleEndpoint,
    loadEndpointDetails,
    handlePageChange,
    clearFilters,
    refresh: loadHosts,
  }
}

export default useHosts
