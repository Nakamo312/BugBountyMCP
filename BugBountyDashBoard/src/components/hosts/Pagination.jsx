import React from 'react'

const Pagination = ({ pagination, onPageChange }) => {
  const { limit, offset, total } = pagination

  if (total <= limit) return null

  return (
    <div className="flex items-center justify-between bg-white rounded-lg shadow p-4">
      <div className="text-sm text-gray-600">
        Showing {offset + 1} to {Math.min(offset + limit, total)} of {total} hosts
      </div>
      <div className="flex space-x-2">
        <button
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          disabled={offset === 0}
          className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(offset + limit)}
          disabled={offset + limit >= total}
          className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  )
}

export default Pagination
