import React from 'react'

const GraphLegend = ({ nodeColors }) => {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 className="font-semibold text-gray-900 mb-3">Legend</h3>
      <div className="space-y-2">
        {Object.entries(nodeColors).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2">
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-sm capitalize">{type}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default GraphLegend
