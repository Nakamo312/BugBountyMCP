import React from 'react'
import { Search, Filter, Loader } from 'lucide-react'

const HostFilters = ({
  searchTerm,
  onSearchChange,
  inScopeFilter,
  onFilterChange,
  onRefresh,
  loading,
}) => {
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center space-x-2">
          <Search className="text-gray-400" size={20} />
          <input
            type="text"
            placeholder="Search hosts..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div className="flex items-center space-x-2">
          <Filter className="text-gray-400" size={20} />
          <select
            value={inScopeFilter === null ? 'all' : inScopeFilter.toString()}
            onChange={(e) => {
              const value = e.target.value
              onFilterChange(value === 'all' ? null : value === 'true')
            }}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="all">All Hosts</option>
            <option value="true">In Scope Only</option>
            <option value="false">Out of Scope Only</option>
          </select>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
        >
          {loading ? <Loader className="animate-spin" size={16} /> : 'Refresh'}
        </button>
      </div>
    </div>
  )
}

export default HostFilters
