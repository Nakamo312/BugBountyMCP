import { useProgram } from '@/context/ProgramContext'
import { useActionRunner } from '@/components/actions/hooks/useActionRunner'
import { useActionCatalog } from '@/components/actions/hooks/useActionCatalog'
import ActionCard from '@/components/actions/ui/ActionCard'
import ActionGrid from '@/components/actions/ui/ActionGrid'

export default function ActionsPage() {
  const { selectedProgram } = useProgram()
  const actionRunner = useActionRunner(selectedProgram)
  const { actions, loading, error } = useActionCatalog()

  if (!selectedProgram) {
    return (
      <div className="text-center py-10 text-gray-500">
        Loading program...
      </div>
    )
  }

  if (loading) {
    return (
      <div className="text-center py-10 text-gray-500">
        Loading action catalog...
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-700">
        Action catalog failed to load: {error}
      </div>
    )
  }

  return (
    <ActionGrid>
      {actions.map(action => (
        <ActionCard
          key={action.id}
          action={action}
          actionRunner={actionRunner}
          active={actionRunner?.activeAction === action.id}
        />
      ))}
    </ActionGrid>
  )
}
