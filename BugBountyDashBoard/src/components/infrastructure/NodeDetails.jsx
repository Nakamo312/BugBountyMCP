import React from 'react'

const NodeDetails = ({ node }) => {
  if (!node) return null

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 className="font-semibold text-gray-900 mb-3">Selected Node</h3>
      <div className="space-y-2 text-sm">
        <div>
          <span className="text-gray-600">Type:</span>{' '}
          <span className="font-medium capitalize">{node.type}</span>
        </div>
        <div>
          <span className="text-gray-600">Label:</span>{' '}
          <span className="font-medium break-all">{node.label}</span>
        </div>
        {node.data && Object.entries(node.data).map(([key, value]) => (
          <div key={key}>
            <span className="text-gray-600">{key}:</span>{' '}
            <span className="font-medium break-all">
              {typeof value === 'object' ? JSON.stringify(value) : String(value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default NodeDetails
