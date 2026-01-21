import { SCANS } from './scans.config'
import { useScanRunner } from './useScanRunner'

export default function ScansPage() {
  const scanRunner = useScanRunner()

  return (
    <ScanGrid>
      {SCANS.map(scan => (
        <ScanCard
          key={scan.id}
          scan={scan}
          active={scanRunner.activeScan === scan.id}
        >
          <ScanFormFactory
            type={scan.form}
            onScan={data => scanRunner.runScan(scan, data)}
            loading={scanRunner.loading}
          />
        </ScanCard>
      ))}
    </ScanGrid>
  )
}
