import { useState } from 'react'

export function useScanRunner(selectedProgram) {
  const [activeScan, setActiveScan] = useState(null)
  const [loading, setLoading] = useState(false)

  async function runScan(scan, formData) {
  setLoading(true)
  setActiveScan(scan.id)
  try {
    const response = await scan.scanFunc({ program_id: selectedProgram.id, ...formData })
    const result = {
      status: response.data.status,
      message: response.data.message,
      results: response.data.results,
    }
    return result
  } catch (err) {
    const errorResult = {
      status: 'error',
      message: err.response?.data?.detail || err.message || 'Scan failed',
      results: null,
    }
    return errorResult
  } finally {
    setLoading(false)
    setActiveScan(null)
  }
}
}
