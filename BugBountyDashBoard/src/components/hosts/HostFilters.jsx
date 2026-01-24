import { Search, Filter, Loader, SortAsc, X } from 'lucide-react'

const HostFilters = ({
  searchTerm,
  onSearchChange,
  inScopeFilter,
  onFilterChange,
  serviceFilter,
  onServiceFilterChange,
  techFilter,
  onTechFilterChange,
  sortBy,
  onSortChange,
  availableServices,
  availableTechs,
  onRefresh,
  loading,
  onClearFilters,
}) => {
  const hasActiveFilters = searchTerm || inScopeFilter !== null || serviceFilter || techFilter

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center space-x-2">
          <Search className="text-gray-400" size={18} />
          <input
            type="text"
            placeholder="Search hosts..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm w-48"
          />
        </div>

        <div className="flex items-center space-x-2">
          <Filter className="text-gray-400" size={18} />
          <select
            value={inScopeFilter === null ? 'all' : inScopeFilter.toString()}
            onChange={(e) => {
              const value = e.target.value
              onFilterChange(value === 'all' ? null : value === 'true')
            }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
          >
            <option value="all">All Scope</option>
            <option value="true">In Scope</option>
            <option value="false">Out of Scope</option>
          </select>
        </div>

        {availableServices && availableServices.length > 0 && (
          <select
            value={serviceFilter || ''}
            onChange={(e) => onServiceFilterChange(e.target.value || null)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
          >
            <option value="">All Services</option>
            {availableServices.map((service) => (
              <option key={service} value={service}>
                {service}
              </option>
            ))}
          </select>
        )}

        {availableTechs && availableTechs.length > 0 && (
          <select
            value={techFilter || ''}
            onChange={(e) => onTechFilterChange(e.target.value || null)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
          >
            <option value="">All Technologies</option>
            {availableTechs.map((tech) => (
              <option key={tech} value={tech}>
                {tech}
              </option>
            ))}
          </select>
        )}

        <div className="flex items-center space-x-2">
          <SortAsc className="text-gray-400" size={18} />
          <select
            value={sortBy}
            onChange={(e) => onSortChange(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
          >
            <option value="host">Host A-Z</option>
            <option value="-host">Host Z-A</option>
            <option value="-endpoint_count">Most Endpoints</option>
            <option value="endpoint_count">Least Endpoints</option>
            <option value="-parameter_count">Most Parameters</option>
            <option value="parameter_count">Least Parameters</option>
          </select>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {hasActiveFilters && (
            <button
              onClick={onClearFilters}
              className="flex items-center space-x-1 px-3 py-1.5 text-gray-600 hover:text-gray-800 text-sm"
            >
              <X size={14} />
              <span>Clear</span>
            </button>
          )}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-4 py-1.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm"
          >
            {loading ? <Loader className="animate-spin" size={14} /> : 'Refresh'}
          </button>
        </div>
      </div>

      {hasActiveFilters && (
        <div className="flex flex-wrap gap-2 text-xs">
          {searchTerm && (
            <span className="px-2 py-1 bg-gray-100 rounded-full">
              Search: "{searchTerm}"
            </span>
          )}
          {inScopeFilter !== null && (
            <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full">
              {inScopeFilter ? 'In Scope' : 'Out of Scope'}
            </span>
          )}
          {serviceFilter && (
            <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded-full">
              Service: {serviceFilter}
            </span>
          )}
          {techFilter && (
            <span className="px-2 py-1 bg-indigo-100 text-indigo-800 rounded-full">
              Tech: {techFilter}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

export default HostFilters
