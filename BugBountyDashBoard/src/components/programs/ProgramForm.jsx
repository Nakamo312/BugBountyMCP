import React from 'react'
import { ChevronDown, ChevronUp, Globe, Link, Loader, Save, Trash2, X } from 'lucide-react'
import { actionBadgeClass, inputTypeIcon } from './programUi'

const ScopeRulesEditor = ({
  formData,
  newScopeRule,
  onAdd,
  onChangeNewRule,
  onRemove,
  onToggle,
  showScopeRules,
}) => (
  <div className="border rounded-lg p-4">
    <button type="button" onClick={onToggle} className="flex items-center justify-between w-full text-left mb-2">
      <div className="flex items-center space-x-2">
        <Globe size={18} className="text-gray-500" />
        <span className="font-medium text-gray-900">Scope Rules</span>
        <span className="text-sm text-gray-500">({formData.scope_rules.length} rules)</span>
      </div>
      {showScopeRules ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
    </button>

    {showScopeRules && (
      <div className="space-y-4 mt-4">
        <div className="bg-gray-50 p-4 rounded-lg space-y-3">
          <div className="flex space-x-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-700 mb-1">Pattern (e.g., *.example.com)</label>
              <input
                type="text"
                value={newScopeRule.pattern}
                onChange={(event) => onChangeNewRule({ ...newScopeRule, pattern: event.target.value })}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                placeholder="*.tinkoff.ru"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
              <select
                value={newScopeRule.rule_type}
                onChange={(event) => onChangeNewRule({ ...newScopeRule, rule_type: event.target.value })}
                className="px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
              >
                <option value="domain">Domain</option>
                <option value="regex">Regex</option>
                <option value="ip_range">IP Range</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Action</label>
              <select
                value={newScopeRule.action}
                onChange={(event) => onChangeNewRule({ ...newScopeRule, action: event.target.value })}
                className="px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
              >
                <option value="include">Include</option>
                <option value="exclude">Exclude</option>
              </select>
            </div>
          </div>
          <button type="button" onClick={onAdd} className="px-3 py-1 text-sm bg-primary-600 text-white rounded hover:bg-primary-700">
            Add Scope Rule
          </button>
        </div>

        {formData.scope_rules.length > 0 ? (
          <div className="space-y-2">
            {formData.scope_rules.map((rule, index) => (
              <div key={`${rule.action}:${rule.rule_type}:${rule.pattern}:${index}`} className="flex items-center justify-between bg-white border rounded p-3">
                <div className="flex items-center space-x-3">
                  <span className={`px-2 py-1 text-xs rounded ${actionBadgeClass(rule.action)}`}>{rule.action}</span>
                  <span className="font-medium text-gray-900">{rule.pattern}</span>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">{rule.rule_type}</span>
                </div>
                <button type="button" onClick={() => onRemove(index)} className="text-gray-400 hover:text-red-600">
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
)

const RootInputsEditor = ({
  formData,
  newRootInput,
  onAdd,
  onChangeNewInput,
  onRemove,
  onToggle,
  showRootInputs,
}) => (
  <div className="border rounded-lg p-4">
    <button type="button" onClick={onToggle} className="flex items-center justify-between w-full text-left mb-2">
      <div className="flex items-center space-x-2">
        <Link size={18} className="text-gray-500" />
        <span className="font-medium text-gray-900">Root Inputs</span>
        <span className="text-sm text-gray-500">({formData.root_inputs.length} inputs)</span>
      </div>
      {showRootInputs ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
    </button>

    {showRootInputs && (
      <div className="space-y-4 mt-4">
        <div className="bg-gray-50 p-4 rounded-lg space-y-3">
          <div className="flex space-x-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-700 mb-1">Value (domain, IP, or URL)</label>
              <input
                type="text"
                value={newRootInput.value}
                onChange={(event) => onChangeNewInput({ ...newRootInput, value: event.target.value })}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                placeholder="example.com or 192.168.1.1"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
              <select
                value={newRootInput.input_type}
                onChange={(event) => onChangeNewInput({ ...newRootInput, input_type: event.target.value })}
                className="px-3 py-2 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
              >
                <option value="domain">Domain</option>
                <option value="ip">IP</option>
                <option value="url">URL</option>
              </select>
            </div>
          </div>
          <button type="button" onClick={onAdd} className="px-3 py-1 text-sm bg-primary-600 text-white rounded hover:bg-primary-700">
            Add Root Input
          </button>
        </div>

        {formData.root_inputs.length > 0 ? (
          <div className="space-y-2">
            {formData.root_inputs.map((input, index) => (
              <div key={`${input.input_type}:${input.value}:${index}`} className="flex items-center justify-between bg-white border rounded p-3">
                <div className="flex items-center space-x-3">
                  <div className="text-gray-500">{inputTypeIcon(input.input_type)}</div>
                  <span className="font-medium text-gray-900">{input.value}</span>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">{input.input_type}</span>
                </div>
                <button type="button" onClick={() => onRemove(index)} className="text-gray-400 hover:text-red-600">
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
)

export const ProgramForm = ({
  addRootInput,
  addScopeRule,
  closeForm,
  editingProgram,
  formData,
  loading,
  newRootInput,
  newScopeRule,
  removeRootInput,
  removeScopeRule,
  setNewRootInput,
  setNewScopeRule,
  setShowRootInputs,
  setShowScopeRules,
  showRootInputs,
  showScopeRules,
  submitProgram,
  updateProgramName,
}) => (
  <div className="bg-white rounded-lg shadow p-6">
    <div className="flex items-center justify-between mb-6">
      <h2 className="text-xl font-semibold text-gray-900">{editingProgram ? 'Edit Program' : 'Create New Program'}</h2>
      <button onClick={closeForm} className="text-gray-400 hover:text-gray-600">
        <X size={20} />
      </button>
    </div>

    <form onSubmit={submitProgram} className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Program Name *</label>
        <input
          type="text"
          value={formData.name}
          onChange={(event) => updateProgramName(event.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          placeholder="e.g., Acme Corp Bug Bounty"
          required
        />
      </div>

      <ScopeRulesEditor
        formData={formData}
        newScopeRule={newScopeRule}
        onAdd={addScopeRule}
        onChangeNewRule={setNewScopeRule}
        onRemove={removeScopeRule}
        onToggle={() => setShowScopeRules(!showScopeRules)}
        showScopeRules={showScopeRules}
      />

      <RootInputsEditor
        formData={formData}
        newRootInput={newRootInput}
        onAdd={addRootInput}
        onChangeNewInput={setNewRootInput}
        onRemove={removeRootInput}
        onToggle={() => setShowRootInputs(!showRootInputs)}
        showRootInputs={showRootInputs}
      />

      <div className="flex space-x-3 pt-4">
        <button
          type="submit"
          disabled={loading}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
        >
          {loading ? <Loader className="animate-spin" size={16} /> : <Save size={16} />}
          <span>{editingProgram ? 'Update' : 'Create'}</span>
        </button>
        <button type="button" onClick={closeForm} className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </form>
  </div>
)
