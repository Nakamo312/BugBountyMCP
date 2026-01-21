// ScansPage.jsx
import { useProgram } from '@/context/ProgramContext'
import { useScanRunner } from '@/components/scans/hooks/useScanRunner'

export default function ScansPage() {
  const { selectedProgram } = useProgram()   
  const scanRunner = useScanRunner(selectedProgram)
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
