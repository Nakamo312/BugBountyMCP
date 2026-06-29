import React from 'react'
import { Globe, Hash, Link } from 'lucide-react'

export const actionBadgeClass = (action) => (
  action === 'include' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
)

export const inputTypeIcon = (type) => {
  switch (type) {
    case 'domain':
      return React.createElement(Globe, { size: 14 })
    case 'ip':
      return React.createElement(Hash, { size: 14 })
    case 'url':
      return React.createElement(Link, { size: 14 })
    default:
      return React.createElement(Globe, { size: 14 })
  }
}
