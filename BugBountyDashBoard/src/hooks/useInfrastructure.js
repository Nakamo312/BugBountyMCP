import { useState, useEffect, useCallback, useMemo } from 'react'
import { getInfrastructureGraph } from '../services/api'

const NODE_COLORS = {
  asn: '#ef4444',
  cidr: '#f97316',
  ip: '#eab308',
  service: '#22c55e',
  host: '#3b82f6',
}

const NODE_SIZES = {
  asn: 12,
  cidr: 10,
  ip: 6,
  service: 5,
  host: 8,
}

export const useInfrastructure = (selectedProgram) => {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [rawData, setRawData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [stats, setStats] = useState({})
  const [filters, setFilters] = useState({
    showASN: true,
    showCIDR: true,
    showIP: true,
    showService: true,
    showHost: true,
  })

  const loadGraph = useCallback(async () => {
    if (!selectedProgram) return

    setLoading(true)
    setError(null)
    try {
      const response = await getInfrastructureGraph(selectedProgram.id)
      setRawData(response.data)
      setStats(response.data.stats || {})
    } catch (err) {
      console.error('Failed to load infrastructure graph:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [selectedProgram])

  useEffect(() => {
    if (selectedProgram) {
      loadGraph()
    }
  }, [selectedProgram, loadGraph])

  const filteredGraphData = useMemo(() => {
    if (!rawData) return { nodes: [], links: [] }

    const visibleNodes = rawData.nodes.filter(node => {
      if (node.type === 'asn' && !filters.showASN) return false
      if (node.type === 'cidr' && !filters.showCIDR) return false
      if (node.type === 'ip' && !filters.showIP) return false
      if (node.type === 'service' && !filters.showService) return false
      if (node.type === 'host' && !filters.showHost) return false
      return true
    })

    const visibleNodeIds = new Set(visibleNodes.map(n => n.id))

    const visibleLinks = rawData.edges
      .filter(edge => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
      .map(edge => ({
        source: edge.source,
        target: edge.target,
        type: edge.type,
      }))

    const nodes = visibleNodes.map(node => ({
      id: node.id,
      label: node.label,
      type: node.type,
      color: NODE_COLORS[node.type] || '#666',
      size: NODE_SIZES[node.type] || 6,
      data: node.data,
    }))

    return { nodes, links: visibleLinks }
  }, [rawData, filters])

  useEffect(() => {
    setGraphData(filteredGraphData)
  }, [filteredGraphData])

  const toggleFilter = (filterName) => {
    setFilters(prev => ({
      ...prev,
      [filterName]: !prev[filterName],
    }))
  }

  return {
    graphData,
    loading,
    error,
    stats,
    filters,
    toggleFilter,
    refresh: loadGraph,
    nodeColors: NODE_COLORS,
  }
}

export default useInfrastructure
