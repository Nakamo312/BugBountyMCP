import React from 'react'
import { AlertCircle, Edit, Trash2 } from 'lucide-react'

export const ProgramList = ({ onCreate, onDelete, onEdit, onSelect, programs, selectedProgram, showForm }) => (
  <>
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {programs.map((program) => (
        <div
          key={program.id}
          className={`bg-white rounded-lg shadow p-6 border-2 transition-colors ${
            selectedProgram?.id === program.id ? 'border-primary-500 bg-primary-50' : 'border-transparent hover:border-gray-200'
          }`}
        >
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 mb-1">{program.name}</h3>
              <p className="text-xs text-gray-500 font-mono truncate">{program.id}</p>
            </div>
            <div className="flex space-x-2 ml-2">
              <button
                onClick={() => onEdit(program)}
                className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                title="Edit"
              >
                <Edit size={16} />
              </button>
              <button
                onClick={() => onDelete(program.id)}
                className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                title="Delete"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
          <button
            onClick={() => onSelect(program)}
            className={`w-full px-4 py-2 rounded-lg transition-colors ${
              selectedProgram?.id === program.id ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {selectedProgram?.id === program.id ? 'Selected' : 'Select Program'}
          </button>
        </div>
      ))}
    </div>

    {programs.length === 0 && !showForm && (
      <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center">
        <AlertCircle className="mx-auto text-gray-400" size={48} />
        <h3 className="mt-4 text-lg font-medium text-gray-900">No programs yet</h3>
        <p className="mt-2 text-sm text-gray-600">Create your first bug bounty program to get started</p>
        <button onClick={onCreate} className="mt-6 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          Create Program
        </button>
      </div>
    )}
  </>
)
