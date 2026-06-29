import { useCallback, useEffect, useState } from 'react'
import { useProgram } from '../context/ProgramContext'
import { createProgram, deleteProgram, getProgram, updateProgram } from '../services/api'

const emptyProgramForm = () => ({
  name: '',
  scope_rules: [],
  root_inputs: [],
})

const emptyScopeRule = () => ({ rule_type: 'domain', pattern: '', action: 'include' })
const emptyRootInput = () => ({ value: '', input_type: 'domain' })

const programErrorMessage = (error) => error.response?.data?.detail || error.message

export const useProgramsManager = () => {
  const { programs, loadPrograms, selectedProgram, selectProgram } = useProgram()
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [editingProgram, setEditingProgram] = useState(null)
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState(emptyProgramForm)
  const [showScopeRules, setShowScopeRules] = useState(false)
  const [showRootInputs, setShowRootInputs] = useState(false)
  const [newScopeRule, setNewScopeRule] = useState(emptyScopeRule)
  const [newRootInput, setNewRootInput] = useState(emptyRootInput)

  useEffect(() => {
    loadPrograms()
  }, [loadPrograms])

  const resetDraft = useCallback(() => {
    setFormData(emptyProgramForm())
    setNewScopeRule(emptyScopeRule())
    setNewRootInput(emptyRootInput())
  }, [])

  const closeForm = useCallback(() => {
    setShowCreateForm(false)
    setEditingProgram(null)
    resetDraft()
  }, [resetDraft])

  const openCreateForm = useCallback(() => {
    resetDraft()
    setEditingProgram(null)
    setShowCreateForm(true)
  }, [resetDraft])

  const submitCreate = useCallback(async () => {
    setLoading(true)
    try {
      await createProgram(formData)
      await loadPrograms()
      closeForm()
    } catch (error) {
      alert(`Failed to create program: ${programErrorMessage(error)}`)
    } finally {
      setLoading(false)
    }
  }, [closeForm, formData, loadPrograms])

  const submitUpdate = useCallback(async () => {
    if (!editingProgram) return
    setLoading(true)
    try {
      await updateProgram(editingProgram, formData)
      await loadPrograms()
      closeForm()
    } catch (error) {
      alert(`Failed to update program: ${programErrorMessage(error)}`)
    } finally {
      setLoading(false)
    }
  }, [closeForm, editingProgram, formData, loadPrograms])

  const submitProgram = useCallback(
    async (event) => {
      event.preventDefault()
      if (editingProgram) {
        await submitUpdate()
      } else {
        await submitCreate()
      }
    },
    [editingProgram, submitCreate, submitUpdate],
  )

  const deleteSelectedProgram = useCallback(
    async (programId) => {
      if (!confirm('Are you sure you want to delete this program and all its data?')) return

      setLoading(true)
      try {
        await deleteProgram(programId)
        await loadPrograms()
        if (selectedProgram?.id === programId) {
          selectProgram(null)
        }
      } catch (error) {
        alert(`Failed to delete program: ${programErrorMessage(error)}`)
      } finally {
        setLoading(false)
      }
    },
    [loadPrograms, selectedProgram, selectProgram],
  )

  const startEdit = useCallback(async (program) => {
    try {
      const response = await getProgram(program.id)
      const data = response.data
      setFormData({
        name: data.program.name,
        scope_rules: data.scope_rules || [],
        root_inputs: data.root_inputs || [],
      })
      setShowCreateForm(false)
      setEditingProgram(program.id)
    } catch (error) {
      alert('Failed to load program details')
    }
  }, [])

  const addScopeRule = useCallback(() => {
    if (!newScopeRule.pattern.trim()) {
      alert('Please enter a pattern for the scope rule')
      return
    }

    setFormData((current) => ({
      ...current,
      scope_rules: [...current.scope_rules, { ...newScopeRule }],
    }))
    setNewScopeRule(emptyScopeRule())
  }, [newScopeRule])

  const removeScopeRule = useCallback((index) => {
    setFormData((current) => ({
      ...current,
      scope_rules: current.scope_rules.filter((_, currentIndex) => currentIndex !== index),
    }))
  }, [])

  const addRootInput = useCallback(() => {
    if (!newRootInput.value.trim()) {
      alert('Please enter a value for the root input')
      return
    }

    setFormData((current) => ({
      ...current,
      root_inputs: [...current.root_inputs, { ...newRootInput }],
    }))
    setNewRootInput(emptyRootInput())
  }, [newRootInput])

  const removeRootInput = useCallback((index) => {
    setFormData((current) => ({
      ...current,
      root_inputs: current.root_inputs.filter((_, currentIndex) => currentIndex !== index),
    }))
  }, [])

  const updateProgramName = useCallback((name) => {
    setFormData((current) => ({ ...current, name }))
  }, [])

  return {
    addRootInput,
    addScopeRule,
    closeForm,
    deleteSelectedProgram,
    editingProgram,
    formData,
    loading,
    newRootInput,
    newScopeRule,
    openCreateForm,
    programs,
    removeRootInput,
    removeScopeRule,
    selectedProgram,
    selectProgram,
    setNewRootInput,
    setNewScopeRule,
    setShowRootInputs,
    setShowScopeRules,
    showCreateForm,
    showRootInputs,
    showScopeRules,
    startEdit,
    submitProgram,
    updateProgramName,
  }
}
