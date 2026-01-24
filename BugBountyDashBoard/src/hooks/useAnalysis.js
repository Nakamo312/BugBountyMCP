import { useState, useEffect, useCallback } from 'react'
import {
  getInjectionCandidates,
  getSSRFCandidates,
  getIDORCandidates,
  getFileUploadCandidates,
  getReflectedParameters,
  getArjunCandidates,
  getAdminDebugEndpoints,
  getCORSAnalysis,
  getSensitiveHeaders,
  getHostTechnologies,
  getSubdomainTakeoverCandidates,
  getAPIPatterns,
} from '../services/api'

const CATEGORIES = {
  injection: {
    label: 'Injection Candidates',
    description: 'SQL injection, XSS, command injection',
    color: 'red',
    fetcher: getInjectionCandidates,
  },
  ssrf: {
    label: 'SSRF Candidates',
    description: 'Server-side request forgery',
    color: 'orange',
    fetcher: getSSRFCandidates,
  },
  idor: {
    label: 'IDOR Candidates',
    description: 'Insecure direct object references',
    color: 'yellow',
    fetcher: getIDORCandidates,
  },
  fileUpload: {
    label: 'File Upload',
    description: 'File upload endpoints',
    color: 'purple',
    fetcher: getFileUploadCandidates,
  },
  reflected: {
    label: 'Reflected Parameters',
    description: 'Parameters reflected in response',
    color: 'pink',
    fetcher: getReflectedParameters,
  },
  arjun: {
    label: 'Arjun Candidates',
    description: 'Hidden parameter discovery targets',
    color: 'blue',
    fetcher: getArjunCandidates,
  },
  adminDebug: {
    label: 'Admin/Debug Endpoints',
    description: 'Administrative and debug paths',
    color: 'red',
    fetcher: getAdminDebugEndpoints,
  },
  cors: {
    label: 'CORS Analysis',
    description: 'Cross-origin resource sharing',
    color: 'green',
    fetcher: getCORSAnalysis,
  },
  sensitiveHeaders: {
    label: 'Sensitive Headers',
    description: 'Headers with sensitive data',
    color: 'amber',
    fetcher: getSensitiveHeaders,
  },
  technologies: {
    label: 'Technologies',
    description: 'Detected technologies',
    color: 'indigo',
    fetcher: getHostTechnologies,
  },
  subdomainTakeover: {
    label: 'Subdomain Takeover',
    description: 'Potential takeover candidates',
    color: 'red',
    fetcher: getSubdomainTakeoverCandidates,
  },
  apiPatterns: {
    label: 'API Patterns',
    description: 'Common API path patterns',
    color: 'cyan',
    fetcher: getAPIPatterns,
  },
}

export const useAnalysis = (selectedProgram) => {
  const [activeCategory, setActiveCategory] = useState('injection')
  const [data, setData] = useState({})
  const [loading, setLoading] = useState({})
  const [counts, setCounts] = useState({})
  const [pagination, setPagination] = useState({ limit: 50, offset: 0 })

  const loadCounts = useCallback(async () => {
    if (!selectedProgram) return

    const newCounts = {}
    await Promise.all(
      Object.entries(CATEGORIES).map(async ([key, { fetcher }]) => {
        try {
          const response = await fetcher(selectedProgram.id, { limit: 1, offset: 0 })
          newCounts[key] = response.data.total || 0
        } catch (error) {
          newCounts[key] = 0
        }
      })
    )
    setCounts(newCounts)
  }, [selectedProgram])

  const loadCategory = useCallback(async (category) => {
    if (!selectedProgram) return

    const config = CATEGORIES[category]
    if (!config) return

    setLoading(prev => ({ ...prev, [category]: true }))
    try {
      const response = await config.fetcher(selectedProgram.id, {
        limit: pagination.limit,
        offset: pagination.offset,
      })
      setData(prev => ({
        ...prev,
        [category]: {
          items: response.data.items || [],
          total: response.data.total || 0,
        },
      }))
    } catch (error) {
      console.error(`Failed to load ${category}:`, error)
      setData(prev => ({
        ...prev,
        [category]: { items: [], total: 0, error: error.message },
      }))
    } finally {
      setLoading(prev => ({ ...prev, [category]: false }))
    }
  }, [selectedProgram, pagination])

  useEffect(() => {
    if (selectedProgram) {
      loadCounts()
    }
  }, [selectedProgram, loadCounts])

  useEffect(() => {
    if (selectedProgram && activeCategory) {
      loadCategory(activeCategory)
    }
  }, [selectedProgram, activeCategory, pagination, loadCategory])

  const handlePageChange = (newOffset) => {
    setPagination(prev => ({ ...prev, offset: newOffset }))
  }

  const refresh = () => {
    loadCounts()
    loadCategory(activeCategory)
  }

  return {
    categories: CATEGORIES,
    activeCategory,
    setActiveCategory,
    data,
    loading,
    counts,
    pagination,
    handlePageChange,
    refresh,
  }
}

export default useAnalysis
