import BaseScanForm from '../forms/BaseScanForm'
import { SCANS } from '@components/scans/configs/scans.config'

export default function ScanFormFactory({ type, onScan, loading }) {
  const scan = SCANS.find(s => s.form === type)

  if (!scan) {
    return (
      <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Unknown scan form: <b>{type}</b>
      </div>
    )
  }

  return (
    <BaseScanForm
      fields={scan.fields}
      initialValues={scan.initialValues}
      onScan={onScan}
      loading={loading}
    />
  )
}
