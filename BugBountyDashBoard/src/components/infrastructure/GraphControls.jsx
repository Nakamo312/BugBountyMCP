import React from 'react'
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'

const GraphControls = ({ graphRef }) => {
  const handleZoomIn = () => {
    if (graphRef.current) {
      graphRef.current.zoom(graphRef.current.zoom() * 1.5, 300)
    }
  }

  const handleZoomOut = () => {
    if (graphRef.current) {
      graphRef.current.zoom(graphRef.current.zoom() / 1.5, 300)
    }
  }

  const handleFitView = () => {
    if (graphRef.current) {
      graphRef.current.zoomToFit(400)
    }
  }

  return (
    <div className="absolute bottom-4 right-4 flex flex-col gap-2">
      <button
        onClick={handleZoomIn}
        className="p-2 bg-white rounded shadow hover:bg-gray-50"
        title="Zoom In"
      >
        <ZoomIn className="w-5 h-5" />
      </button>
      <button
        onClick={handleZoomOut}
        className="p-2 bg-white rounded shadow hover:bg-gray-50"
        title="Zoom Out"
      >
        <ZoomOut className="w-5 h-5" />
      </button>
      <button
        onClick={handleFitView}
        className="p-2 bg-white rounded shadow hover:bg-gray-50"
        title="Fit to View"
      >
        <Maximize2 className="w-5 h-5" />
      </button>
    </div>
  )
}

export default GraphControls
