import { useState } from 'react'
import BaseScanForm from '../forms/BaseScanForm'
import { SCANS } from '@/components/scans/configs/scans.config'

export default function ScanFormFactory({ type, onScan, scanColor }) {
  const scan = SCANS.find(s => s.form === type)
  const [loading, setLoading] = useState(false)

  if (!scan) {
    return (
      <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Unknown scan form: <b>{type}</b>
      </div>
    )
  }

  const handleScan = async (data) => {
    setLoading(true)
    try {
      const result = await onScan(data)
      return result
    } finally {
      setLoading(false)
    }
  }

  return (
    <BaseScanForm
      fields={scan.fields}
      initialValues={scan.initialValues}
      onScan={handleScan}
      loading={loading}
      submitLabel={scan.label || 'Run Scan'}
      scanColor={scanColor || 'blue'}
    />
  )
}
