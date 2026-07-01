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
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-6 text-sm text-yellow-800">
        Select a program to load the action catalog.
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
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Action Catalog</h1>
        <p className="mt-2 text-gray-600">Executable capabilities available to ActionService. Workbench node actions should be derived from this catalog, not hardcoded in the browser.</p>
      </div>
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
    </div>
  )
}
