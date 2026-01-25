import { forwardRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const GraphCanvas = forwardRef(({ graphData, onNodeClick, loading }, ref) => {
  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const fontSize = Math.max(10 / globalScale, 2)
    ctx.beginPath()
    ctx.arc(node.x, node.y, node.size, 0, 2 * Math.PI)
    ctx.fillStyle = node.color
    ctx.fill()

    if (globalScale > 1) {
      ctx.font = `${fontSize}px Sans-Serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#1f2937'
      ctx.fillText(node.label, node.x, node.y + node.size + fontSize)
    }
  }, [])

  if (loading) {
    return (
      <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-10">
        <div className="flex items-center gap-2 text-blue-600">
          <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>Loading graph...</span>
        </div>
      </div>
    )
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="absolute inset-0 flex items-center justify-center text-gray-500">
        No infrastructure data available
      </div>
    )
  }

  return (
    <ForceGraph2D
      ref={ref}
      graphData={graphData}
      nodeLabel={(node) => `${node.type}: ${node.label}`}
      nodeColor={(node) => node.color}
      nodeVal={(node) => node.size}
      linkColor={() => '#cbd5e1'}
      linkWidth={2}
      linkDirectionalArrowLength={4}
      linkDirectionalArrowRelPos={1}
      linkDirectionalParticles={2}
      linkDirectionalParticleWidth={2}
      onNodeClick={onNodeClick}
      nodeCanvasObject={nodeCanvasObject}
      dagMode="lr"
      dagLevelDistance={150}
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
      warmupTicks={100}
      cooldownTicks={0}
    />
  )
})

GraphCanvas.displayName = 'GraphCanvas'

export default GraphCanvas
