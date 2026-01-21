import { SCANS } from '@/components/scans'
import { useScanRunner } from '@/components/scans/hooks/useScanRunner'
import ScanGrid from '@/components/scans/ui/ScanGrid'
import ScanCard from '@/components/scans/ui/ScanCard'
import ScanFormFactory from '@/components/scans/ui/ScanFormFactory'

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
