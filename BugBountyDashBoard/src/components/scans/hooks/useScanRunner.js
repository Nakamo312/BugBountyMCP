import { useState } from 'react'

export function useScanRunner() {
  const [activeScan, setActiveScan] = useState(null)
  const [loading, setLoading] = useState(false)

  const runScan = async (scan, formData) => {
    if (!scan?.api) {
      console.warn('No API defined for scan:', scan?.id)
      return
    }

    try {
      setActiveScan(scan.id)
      setLoading(true)

      const result = await scan.api({
        program_id: selectedProgram.id,
        ...formData,
      })

      console.log(`Scan ${scan.name} finished:`, result)
      return result
    } catch (error) {
      console.error(`Error running scan ${scan.name}:`, error)
      throw error
    } finally {
      setLoading(false)
    }
  }

  return {
    activeScan,
    loading,
    runScan,
  }
}
