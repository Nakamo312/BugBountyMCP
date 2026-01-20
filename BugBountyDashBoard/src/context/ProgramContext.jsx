import React, { createContext, useContext, useState, useEffect } from 'react'
import { listPrograms } from '../services/api'

const ProgramContext = createContext()

export const useProgram = () => {
  const context = useContext(ProgramContext)
  if (!context) {
    throw new Error('useProgram must be used within a ProgramProvider')
  }
  return context
}

export const ProgramProvider = ({ children }) => {
  const [selectedProgram, setSelectedProgram] = useState(null)
  const [programs, setPrograms] = useState([])
  const [loading, setLoading] = useState(false)

  const loadPrograms = async () => {
    setLoading(true)
    try {
      const response = await listPrograms()
      setPrograms(response.data)
      // Auto-select first program if available and none selected
      if (response.data.length > 0 && !selectedProgram) {
        setSelectedProgram(response.data[0])
      }
    } catch (error) {
      console.error('Failed to load programs:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPrograms()
  }, [])

  const selectProgram = (program) => {
    setSelectedProgram(program)
    // Store in localStorage
    localStorage.setItem('selectedProgramId', program.id)
  }

  useEffect(() => {
    // Restore selected program from localStorage
    const savedProgramId = localStorage.getItem('selectedProgramId')
    if (savedProgramId && programs.length > 0) {
      const program = programs.find(p => p.id === savedProgramId)
      if (program) {
        setSelectedProgram(program)
      }
    }
  }, [programs])

  return (
    <ProgramContext.Provider value={{
      selectedProgram,
      selectProgram,
      programs,
      loadPrograms,
      loading,
    }}>
      {children}
    </ProgramContext.Provider>
  )
}
