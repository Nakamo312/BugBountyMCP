import React, { useState, useEffect } from 'react'
import { useProgram } from '../context/ProgramContext'
import { createProgram, updateProgram, deleteProgram, getProgram } from '../services/api'
import { Plus, Edit, Trash2, Save, X, AlertCircle, Loader, Globe, Hash, Link, ChevronDown, ChevronUp } from 'lucide-react'

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
  const [showScopeRules, setShowScopeRules] = useState(false)
  const [showRootInputs, setShowRootInputs] = useState(false)
  const [newScopeRule, setNewScopeRule] = useState({ rule_type: 'domain', pattern: '', action: 'include' })
  const [newRootInput, setNewRootInput] = useState({ value: '', input_type: 'domain' })

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
      setNewScopeRule({ rule_type: 'domain', pattern: '', action: 'include' })
      setNewRootInput({ value: '', input_type: 'domain' })
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
      setNewScopeRule({ rule_type: 'domain', pattern: '', action: 'include' })
      setNewRootInput({ value: '', input_type: 'domain' })
    } catch (error) {
      alert('Failed to update program: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (programId) => {
    if (!confirm('Are you sure you want to delete this program and all its data?')) return
    
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

  const addScopeRule = () => {
    if (!newScopeRule.pattern.trim()) {
      alert('Please enter a pattern for the scope rule')
      return
    }
    
    setFormData({
      ...formData,
      scope_rules: [...formData.scope_rules, { ...newScopeRule }]
    })
    setNewScopeRule({ rule_type: 'domain', pattern: '', action: 'include' })
  }

  const removeScopeRule = (index) => {
    const newRules = [...formData.scope_rules]
    newRules.splice(index, 1)
    setFormData({ ...formData, scope_rules: newRules })
  }

  const addRootInput = () => {
    if (!newRootInput.value.trim()) {
      alert('Please enter a value for the root input')
      return
    }
    
    setFormData({
      ...formData,
      root_inputs: [...formData.root_inputs, { ...newRootInput }]
    })
    setNewRootInput({ value: '', input_type: 'domain' })
  }

  const removeRootInput = (index) => {
    const newInputs = [...formData.root_inputs]
    newInputs.splice(index, 1)
    setFormData({ ...formData, root_inputs: newInputs })
  }

  const getActionColor = (action) => {
    return action === 'include' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
  }

  const getInputTypeIcon = (type) => {
    switch (type) {
      case 'domain': return <Globe size={14} />
      case 'ip': return <Hash size={14} />
      case 'url': return <Link size={14} />
      default: return <Globe size={14} />
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

      {/* Create/Edit Form */}
      {(showCreateForm || editingProgram) && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-gray-900">
              {editingProgram ? 'Edit Program' : 'Create New Program'}
            </h2>
            <button
              onClick={() => {
                setShowCreateForm(false)
                setEditingProgram(null)
                setFormData({ name: '', scope_rules: [], root_inputs: [] })
                setNewScopeRule({ rule_type: 'domain', pattern: '', action: 'include' })
                setNewRootInput({ value: '', input_type: 'domain' })
              }}
              className="text-gray-400 hover:text-gray-600"
            >
              <X size={20} />
            </button>
          </div>
          
          <form onSubmit={editingProgram ? (e) => { e.preventDefault(); handleUpdate(editingProgram) } : handleCreate} className="space-y-6">
            {/* Program Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Program Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                placeholder="e.g., Acme Corp Bug Bounty"
                required
              />
            </div>

            {/* Scope Rules Section */}
            <div className="border rounded-lg p-4">
              <button
                type="button"
                onClick={() => setShowScopeRules(!showScopeRules)}
                className="flex items-center justify-between w-full text-left mb-2"
              >
                <div className="flex items-center space-x-2">
                  <Globe size={18} className="text-gray-500" />
                  <span className="font-medium text-gray-900">Scope Rules</span>
                  <span className="text-sm text-gray-500">({formData.scope_rules.length} rules)</span>
                </div>
                {showScopeRules ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </button>
              
              {showScopeRules && (
                <div className="space-y-4 mt-4">
                  {/* Add New Scope Rule */}
                  <div className="bg-gray-50 p-4 rounded-lg space-y-3">
                    <div className="flex space-x-3">
                      <div className="flex-1">
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                          Pattern (e.g., *.example.com)
                        </label>
                        <input
                          type="text"
                          value={newScopeRule.pattern}
                          onChange={(e) => setNewScopeRule({ ...newScopeRule, pattern: e.target.value })}
                          className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                          placeholder="*.tinkoff.ru"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                          Type
                        </label>
                        <select
                          value={newScopeRule.rule_type}
                          onChange={(e) => setNewScopeRule({ ...newScopeRule, rule_type: e.target.value })}
                          className="px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                        >
                          <option value="domain">Domain</option>
                          <option value="regex">Regex</option>
                          <option value="ip_range">IP Range</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                          Action
                        </label>
                        <select
                          value={newScopeRule.action}
                          onChange={(e) => setNewScopeRule({ ...newScopeRule, action: e.target.value })}
                          className="px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                        >
                          <option value="include">Include</option>
                          <option value="exclude">Exclude</option>
                        </select>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={addScopeRule}
                      className="px-3 py-1 text-sm bg-primary-600 text-white rounded hover:bg-primary-700"
                    >
                      Add Scope Rule
                    </button>
                  </div>

                  {/* Existing Scope Rules */}
                  {formData.scope_rules.length > 0 ? (
                    <div className="space-y-2">
                      {formData.scope_rules.map((rule, index) => (
                        <div key={index} className="flex items-center justify-between bg-white border rounded p-3">
                          <div className="flex items-center space-x-3">
                            <span className={`px-2 py-1 text-xs rounded ${getActionColor(rule.action)}`}>
                              {rule.action}
                            </span>
                            <span className="font-medium text-gray-900">{rule.pattern}</span>
                            <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                              {rule.rule_type}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeScopeRule(index)}
                            className="text-gray-400 hover:text-red-600"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500 italic">No scope rules added yet</p>
                  )}
                </div>
              )}
            </div>

            {/* Root Inputs Section */}
            <div className="border rounded-lg p-4">
              <button
                type="button"
                onClick={() => setShowRootInputs(!showRootInputs)}
                className="flex items-center justify-between w-full text-left mb-2"
              >
                <div className="flex items-center space-x-2">
                  <Link size={18} className="text-gray-500" />
                  <span className="font-medium text-gray-900">Root Inputs</span>
                  <span className="text-sm text-gray-500">({formData.root_inputs.length} inputs)</span>
                </div>
                {showRootInputs ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </button>
              
              {showRootInputs && (
                <div className="space-y-4 mt-4">
                  {/* Add New Root Input */}
                  <div className="bg-gray-50 p-4 rounded-lg space-y-3">
                    <div className="flex space-x-3">
                      <div className="flex-1">
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                          Value (domain, IP, or URL)
                        </label>
                        <input
                          type="text"
                          value={newRootInput.value}
                          onChange={(e) => setNewRootInput({ ...newRootInput, value: e.target.value })}
                          className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                          placeholder="example.com or 192.168.1.1"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                          Type
                        </label>
                        <select
                          value={newRootInput.input_type}
                          onChange={(e) => setNewRootInput({ ...newRootInput, input_type: e.target.value })}
                          className="px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                        >
                          <option value="domain">Domain</option>
                          <option value="ip">IP</option>
                          <option value="url">URL</option>
                        </select>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={addRootInput}
                      className="px-3 py-1 text-sm bg-primary-600 text-white rounded hover:bg-primary-700"
                    >
                      Add Root Input
                    </button>
                  </div>

                  {/* Existing Root Inputs */}
                  {formData.root_inputs.length > 0 ? (
                    <div className="space-y-2">
                      {formData.root_inputs.map((input, index) => (
                        <div key={index} className="flex items-center justify-between bg-white border rounded p-3">
                          <div className="flex items-center space-x-3">
                            <div className="text-gray-500">
                              {getInputTypeIcon(input.input_type)}
                            </div>
                            <span className="font-medium text-gray-900">{input.value}</span>
                            <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                              {input.input_type}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeRootInput(index)}
                            className="text-gray-400 hover:text-red-600"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500 italic">No root inputs added yet</p>
                  )}
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex space-x-3 pt-4">
              <button
                type="submit"
                disabled={loading}
                className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                {loading ? <Loader className="animate-spin" size={16} /> : <Save size={16} />}
                <span>{editingProgram ? 'Update' : 'Create'}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowCreateForm(false)
                  setEditingProgram(null)
                  setFormData({ name: '', scope_rules: [], root_inputs: [] })
                  setNewScopeRule({ rule_type: 'domain', pattern: '', action: 'include' })
                  setNewRootInput({ value: '', input_type: 'domain' })
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
              {selectedProgram?.id === program.id ? 'Selected' : 'Select Program'}
            </button>
          </div>
        ))}
      </div>

      {programs.length === 0 && !showCreateForm && !editingProgram && (
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