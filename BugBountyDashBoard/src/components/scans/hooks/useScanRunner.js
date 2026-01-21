import { useState } from 'react'

export function useScanRunner(selectedProgram) {
  const [activeScan, setActiveScan] = useState(null)
  const [loading, setLoading] = useState(false)

  async function runScan(scan, formData) {
    if (!selectedProgram) {
      return {
        status: 'error',
        message: 'No program selected',
        results: null,
      }
    }

    if (!scan.api || typeof scan.api !== 'function') {
      return {
        status: 'error',
        message: `API function not defined for scan ${scan.id}`,
        results: null,
      }
    }

    setLoading(true)
    setActiveScan(scan.id)

    try {
      const response = await scan.api({
        program_id: selectedProgram.id,
        ...formData,
      })

      return {
        status: response.data.status,
        message: response.data.message,
        results: response.data.results,
      }
    } catch (err) {
      return {
        status: 'error',
        message: err.response?.data?.detail || err.message || 'Scan failed',
        results: null,
      }
    } finally {
      setLoading(false)
      setActiveScan(null)
    }
  }

  return { runScan, activeScan, loading }
}
