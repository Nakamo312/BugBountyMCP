import React from 'react'

const GraphFilters = ({ filters, toggleFilter, nodeColors }) => {
  const filterItems = [
    { key: 'showASN', type: 'asn', label: 'ASN' },
    { key: 'showCIDR', type: 'cidr', label: 'CIDR' },
    { key: 'showIP', type: 'ip', label: 'IP' },
    { key: 'showService', type: 'service', label: 'Service' },
    { key: 'showHost', type: 'host', label: 'Host' },
  ]

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 className="font-semibold text-gray-900 mb-3">Filters</h3>
      <div className="space-y-2">
        {filterItems.map(({ key, type, label }) => (
          <label key={key} className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={filters[key]}
              onChange={() => toggleFilter(key)}
              className="rounded"
            />
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: nodeColors[type] }}
            />
            <span className="text-sm">{label}</span>
          </label>
        ))}
      </div>
    </div>
  )
}

export default GraphFilters
