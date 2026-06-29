import React from 'react'
import { Plus } from 'lucide-react'
import { ProgramForm, ProgramList } from '../components/programs'
import { useProgramsManager } from '../hooks/useProgramsManager'

const Programs = () => {
  const programsState = useProgramsManager()
  const showForm = programsState.showCreateForm || programsState.editingProgram

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Programs</h1>
          <p className="text-gray-600 mt-2">Manage your bug bounty programs</p>
        </div>
        <button
          onClick={programsState.openCreateForm}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus size={20} />
          <span>New Program</span>
        </button>
      </div>

      {showForm && <ProgramForm {...programsState} />}

      <ProgramList
        onCreate={programsState.openCreateForm}
        onDelete={programsState.deleteSelectedProgram}
        onEdit={programsState.startEdit}
        onSelect={programsState.selectProgram}
        programs={programsState.programs}
        selectedProgram={programsState.selectedProgram}
        showForm={showForm}
      />
    </div>
  )
}

export default Programs
