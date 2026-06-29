import { useEffect, useState } from 'react'
import { getActionCatalogItem, listActionCatalog } from '@/services/api'
import { buildActionFromCatalogDetail } from '../catalog/actionCatalog'

export function useActionCatalog() {
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setLoading(true)
      setError(null)
      try {
        const response = await listActionCatalog()
        const items = response.data?.items || []
        const details = await Promise.all(
          items.map(item => getActionCatalogItem(item.id).then(detail => detail.data))
        )
        if (!cancelled) {
          setActions(details.map(buildActionFromCatalogDetail))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.detail || err.message || 'Action catalog failed to load')
          setActions([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadCatalog()

    return () => {
      cancelled = true
    }
  }, [])

  return { actions, loading, error }
}

export default useActionCatalog
