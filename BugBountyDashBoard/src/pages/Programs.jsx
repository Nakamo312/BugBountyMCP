import React, { useState, useEffect } from 'react'
import { useProgram } from '../context/ProgramContext'
import { createProgram, updateProgram, deleteProgram, getProgram } from '../services/api'
import { Plus, Edit, Trash2, Save, X, AlertCircle, Loader } from 'lucide-react'

const Programs = () => {
  const { programs, loadPrograms, selectedProgram, selectProgram } = useProgram()
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [editingProgram, setEditingProgram] = useState(null)
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    scope_rules: [],
    root_inputs: [],
  })

  useEffect(() => {
    loadPrograms()
  }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await createProgram(formData)
      await loadPrograms()
      setShowCreateForm(false)
      setFormData({ name: '', scope_rules: [], root_inputs: [] })
    } catch (error) {
      alert('Failed to create program: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleUpdate = async (programId) => {
    setLoading(true)
    try {
      await updateProgram(programId, formData)
      await loadPrograms()
      setEditingProgram(null)
      setFormData({ name: '', scope_rules: [], root_inputs: [] })
    } catch (error) {
      alert('Failed to update program: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (programId) => {
    if (!confirm('Are you sure you want to delete this program?')) return
    
    setLoading(true)
    try {
      await deleteProgram(programId)
      await loadPrograms()
      if (selectedProgram?.id === programId) {
        selectProgram(null)
      }
    } catch (error) {
      alert('Failed to delete program: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const startEdit = async (program) => {
    try {
      const response = await getProgram(program.id)
      const data = response.data
      setFormData({
        name: data.program.name,
        scope_rules: data.scope_rules || [],
        root_inputs: data.root_inputs || [],
      })
      setEditingProgram(program.id)
    } catch (error) {
      alert('Failed to load program details')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Programs</h1>
          <p className="text-gray-600 mt-2">Manage your bug bounty programs</p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus size={20} />
          <span>New Program</span>
        </button>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">Create New Program</h2>
            <button
              onClick={() => {
                setShowCreateForm(false)
                setFormData({ name: '', scope_rules: [], root_inputs: [] })
              }}
              className="text-gray-400 hover:text-gray-600"
            >
              <X size={20} />
            </button>
          </div>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Program Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                required
              />
            </div>
            <div className="flex space-x-3">
              <button
                type="submit"
                disabled={loading}
                className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                {loading ? <Loader className="animate-spin" size={16} /> : <Save size={16} />}
                <span>Create</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowCreateForm(false)
                  setFormData({ name: '', scope_rules: [], root_inputs: [] })
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Programs List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {programs.map((program) => (
          <div
            key={program.id}
            className={`bg-white rounded-lg shadow p-6 border-2 transition-colors ${
              selectedProgram?.id === program.id
                ? 'border-primary-500 bg-primary-50'
                : 'border-transparent hover:border-gray-200'
            }`}
          >
            {editingProgram === program.id ? (
              <div className="space-y-4">
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
                <div className="flex space-x-2">
                  <button
                    onClick={() => handleUpdate(program.id)}
                    disabled={loading}
                    className="flex items-center space-x-1 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                  >
                    <Save size={16} />
                    <span>Save</span>
                  </button>
                  <button
                    onClick={() => {
                      setEditingProgram(null)
                      setFormData({ name: '', scope_rules: [], root_inputs: [] })
                    }}
                    className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">{program.name}</h3>
                    <p className="text-xs text-gray-500 font-mono truncate">{program.id}</p>
                  </div>
                  <div className="flex space-x-2 ml-2">
                    <button
                      onClick={() => startEdit(program)}
                      className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                      title="Edit"
                    >
                      <Edit size={16} />
                    </button>
                    <button
                      onClick={() => handleDelete(program.id)}
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => selectProgram(program)}
                  className={`w-full px-4 py-2 rounded-lg transition-colors ${
                    selectedProgram?.id === program.id
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {selectedProgram?.id === program.id ? 'Selected' : 'Select'}
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {programs.length === 0 && !showCreateForm && (
        <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center">
          <AlertCircle className="mx-auto text-gray-400" size={48} />
          <h3 className="mt-4 text-lg font-medium text-gray-900">No programs yet</h3>
          <p className="mt-2 text-sm text-gray-600">
            Create your first bug bounty program to get started
          </p>
          <button
            onClick={() => setShowCreateForm(true)}
            className="mt-6 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            Create Program
          </button>
        </div>
      )}
    </div>
  )
}

export default Programs
