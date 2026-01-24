import React from 'react'

const GraphStats = ({ stats }) => {
  const items = [
    { label: 'ASNs', key: 'asn_count' },
    { label: 'CIDRs', key: 'cidr_count' },
    { label: 'IPs', key: 'ip_count' },
    { label: 'Services', key: 'service_count' },
    { label: 'Hosts', key: 'host_count' },
  ]

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 className="font-semibold text-gray-900 mb-3">Stats</h3>
      <div className="space-y-2 text-sm">
        {items.map(({ label, key }) => (
          <div key={key} className="flex justify-between">
            <span className="text-gray-600">{label}</span>
            <span className="font-medium">{stats[key] || 0}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default GraphStats
