import { useState } from 'react'
import { useProgram } from '@/context/ProgramContext'
import { useScanRunner } from '@/components/scans/hooks/useScanRunner'
import { SCANS } from '@/components/scans'
import ScanCard from '@/components/scans/ui/ScanCard'
import ScanGrid from '@/components/scans/ui/ScanGrid'
import ScanFormFactory from '@/components/scans/ui/ScanFormFactory'
import ScanToast from '@/components/scans/ui/ScanToast'

export default function ScansPage() {
  const { selectedProgram } = useProgram()
  const scanRunner = useScanRunner(selectedProgram)
  const [toastResult, setToastResult] = useState(null)

  const handleRunScan = async (scan, data) => {
    const result = await scanRunner.runScan(scan, data)
    if (result) setToastResult(result) 
  }

  return (
    <>
      <ScanGrid>
        {SCANS.map(scan => (
          <ScanCard
            key={scan.id}
            scan={scan}
            active={scanRunner.activeScan === scan.id}
          >
            <ScanFormFactory
              type={scan.form}
              onScan={data => handleRunScan(scan, data)}
              loading={scanRunner.loading}
            />
          </ScanCard>
        ))}
      </ScanGrid>

      <ScanToast scanResult={toastResult} onClose={() => setToastResult(null)} />
    </>
  )
}
