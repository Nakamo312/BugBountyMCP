export const queueBacklog = (queue = {}) => (queue.pending || 0) + (queue.locked || 0)
export const queueUnhealthy = (queue = {}) => (queue.failed || 0) + (queue.dead || 0)

export const severityBadgeClass = (severity) => {
  if (severity === 'critical') return 'bg-red-100 text-red-800'
  if (severity === 'warning') return 'bg-yellow-100 text-yellow-800'
  return 'bg-blue-100 text-blue-800'
}
