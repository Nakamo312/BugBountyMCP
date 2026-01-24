import React, { useRef, useCallback, useState } from 'react'
import { useProgram } from '../context/ProgramContext'
import { useInfrastructure } from '../hooks/useInfrastructure'
import {
  GraphCanvas,
  GraphControls,
  GraphStats,
  GraphFilters,
  GraphLegend,
  NodeDetails,
} from '../components/infrastructure'
import { RefreshCw } from 'lucide-react'

const InfrastructureMap = () => {
  const { selectedProgram } = useProgram()
  const {
    graphData,
    loading,
    error,
    stats,
    filters,
    toggleFilter,
    refresh,
    nodeColors,
  } = useInfrastructure(selectedProgram)
  const graphRef = useRef()
  const [selectedNode, setSelectedNode] = useState(null)

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node)
    if (graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 500)
      graphRef.current.zoom(2, 500)
    }
  }, [])

  if (!selectedProgram) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-500">
        Select a program to view infrastructure map
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Infrastructure Map</h1>
          <p className="text-gray-600">Network topology visualization for {selectedProgram.name}</p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          Error: {error}
        </div>
      )}

      <div className="grid grid-cols-5 gap-4">
        <div
          className="col-span-4 bg-white rounded-lg shadow-sm border border-gray-200 relative"
          style={{ height: '70vh' }}
        >
          <GraphCanvas
            ref={graphRef}
            graphData={graphData}
            onNodeClick={handleNodeClick}
            loading={loading}
          />
          <GraphControls graphRef={graphRef} />
        </div>

        <div className="space-y-4">
          <GraphStats stats={stats} />
          <GraphFilters
            filters={filters}
            toggleFilter={toggleFilter}
            nodeColors={nodeColors}
          />
          <GraphLegend nodeColors={nodeColors} />
          <NodeDetails node={selectedNode} />
        </div>
      </div>
    </div>
  )
}

export default InfrastructureMap
