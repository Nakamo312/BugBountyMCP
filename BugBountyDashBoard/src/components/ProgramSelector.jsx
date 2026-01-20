import React, { useState } from 'react'
import { useProgram } from '../context/ProgramContext'
import { ChevronDown, Check } from 'lucide-react'

const ProgramSelector = () => {
  const { selectedProgram, selectProgram, programs, loading } = useProgram()
  const [isOpen, setIsOpen] = useState(false)

  if (loading) {
    return (
      <div className="text-sm text-gray-400">Loading programs...</div>
    )
  }

  if (programs.length === 0) {
    return (
      <div className="text-sm text-gray-400">No programs available</div>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="text-xs text-gray-400 mb-1">Active Program</div>
          <div className="text-sm font-medium text-white truncate">
            {selectedProgram?.name || 'Select a program'}
          </div>
        </div>
        <ChevronDown 
          size={18} 
          className={`text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <>
          <div 
            className="fixed inset-0 z-10" 
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full left-0 right-0 mt-2 bg-gray-800 rounded-lg shadow-xl z-20 max-h-64 overflow-y-auto">
            {programs.map((program) => (
              <button
                key={program.id}
                onClick={() => {
                  selectProgram(program)
                  setIsOpen(false)
                }}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-700 transition-colors text-left"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white truncate">
                    {program.name}
                  </div>
                  <div className="text-xs text-gray-400 truncate mt-1 font-mono">
                    {program.id}
                  </div>
                </div>
                {selectedProgram?.id === program.id && (
                  <Check size={18} className="text-primary-400 flex-shrink-0 ml-2" />
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default ProgramSelector
