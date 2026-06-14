import { useState } from 'react'
import { useProgram } from '@/context/ProgramContext'
import { useActionRunner } from '@/components/actions/hooks/useActionRunner'
import { ACTIONS } from '@/components/actions'
import ActionCard from '@/components/actions/ui/ActionCard'
import ActionGrid from '@/components/actions/ui/ActionGrid'
import ActionFormFactory from '@/components/actions/ui/ActionFormFactory'
import ActionToast from '@/components/actions/ui/ActionToast'

export default function ActionsPage() {
  const { selectedProgram } = useProgram()
  const actionRunner = useActionRunner(selectedProgram)
  const [toastResult, setToastResult] = useState(null)

  if (!selectedProgram) {
    return (
      <div className="text-center py-10 text-gray-500">
        Loading program...
      </div>
    )
  }

  const handleRunAction = async (action, data) => {
    const result = await actionRunner.runAction(action, data)
    if (result) setToastResult(result)
  }

  return (
    <>
      <ActionGrid>
        {ACTIONS.map(action => (
          <ActionCard
            key={action.id}
            action={action}
            actionRunner={actionRunner}
            active={actionRunner?.activeAction === action.id}
          >
            <ActionFormFactory
              type={action.form}
              onRun={data => handleRunAction(action, data)}
              loading={actionRunner?.loading || false}
            />
          </ActionCard>
        ))}
      </ActionGrid>

      <ActionToast actionResult={toastResult} onClose={() => setToastResult(null)} />
    </>
  )
}
