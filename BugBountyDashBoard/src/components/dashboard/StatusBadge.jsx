import React from 'react'

export const StatusBadge = ({ ok, label }) => (
  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${ok ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
    {label}
  </span>
)
