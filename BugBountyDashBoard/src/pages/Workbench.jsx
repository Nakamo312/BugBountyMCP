import React, { useEffect, useState } from 'react'
import { AlertCircle, DatabaseZap, Loader, RefreshCw } from 'lucide-react'
import WorkbenchCanvas from '../components/workbench/WorkbenchCanvas'
import { useProgram } from '../context/ProgramContext'
import { useWorkbench } from '../hooks/useWorkbench'
import {
  CommandBar,
  CountBadge,
  Inspector,
  LensSelector,
  LowerEvidencePanel,
  NodeList,
  ProjectionControlPanel,
  ProjectionStatus,
  copyToClipboard,
  emptyCounts,
  loadSavedViews,
  persistSavedViews,
} from '../components/workbench/WorkbenchPanels'

const Workbench = () => {
  const { selectedProgram } = useProgram()
  const [filterQuery, setFilterQuery] = useState('')
  const [savedViews, setSavedViews] = useState([])
  const [showReadModelDetails, setShowReadModelDetails] = useState(false)
  const programId = selectedProgram?.id
  const {
    actionSubmission,
    actionSubmitting,
    actions,
    activeSeed,
    bootstrap,
    entity,
    entityErrors,
    entityLoading,
    error,
    evidencePack,
    focusNode,
    graph,
    lens,
    lenses,
    loading,
    memory,
    projectionResult,
    projectionRunning,
    reload,
    runProjectionRefresh,
    retrieveQuery,
    selectedNode,
    selectNode,
    submitSelectedAction,
    setRetrieveQuery,
  } = useWorkbench(selectedProgram)

  useEffect(() => {
    setSavedViews(loadSavedViews(programId))
  }, [programId])

  if (!selectedProgram) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-6">
        <div className="flex items-center space-x-3">
          <AlertCircle className="text-yellow-600" size={24} />
          <div>
            <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
            <p className="mt-1 text-sm text-yellow-700">Select a program to open the workbench.</p>
          </div>
        </div>
      </div>
    )
  }

  const counts = graph?.counts || bootstrap?.counts || emptyCounts
  const missingProjectionError = /graph not found|component graph not found/i.test(error || '')
  const saveCurrentView = () => {
    const seed = selectedNode?.entity_key || activeSeed || null
    const label = `${lens}${filterQuery ? ` · ${filterQuery}` : ''}${seed ? ' · focused' : ''}`
    setSavedViews((current) => {
      const next = [
        { id: `${Date.now()}`, lens, filter: filterQuery, seed, label },
        ...current.filter((view) => view.lens !== lens || view.filter !== filterQuery || view.seed !== seed),
      ].slice(0, 8)
      persistSavedViews(programId, next)
      return next
    })
  }
  const applySavedView = (view) => {
    setFilterQuery(view.filter || '')
    reload({ nextLens: view.lens, seed: view.seed || null, depth: view.seed ? 2 : 1 })
  }
  const rerankSelected = () => {
    if (selectedNode) selectNode(selectedNode)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Workbench</h1>
          <p className="mt-2 text-gray-600">
            Graph, evidence, memory, and actions for{' '}
            <span className="font-semibold text-primary-600">{selectedProgram.name}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => reload({ nextLens: lens, seed: activeSeed, depth: activeSeed ? 2 : 1 })}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {loading ? <Loader className="animate-spin" size={16} /> : <RefreshCw size={16} />}
          <span>Refresh</span>
        </button>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <LensSelector lens={lens} lenses={lenses} onChange={(nextLens) => reload({ nextLens })} />
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <DatabaseZap size={16} />
            <span>{bootstrap?.projection_freshness?.ui_data_fresh ? 'fresh' : 'stale or unknown'}</span>
          </div>
        </div>
      </div>

      <CommandBar
        retrieveQuery={retrieveQuery}
        setRetrieveQuery={setRetrieveQuery}
        selectedNode={selectedNode}
        onRerunSelected={rerankSelected}
      />

      <ProjectionStatus bootstrap={bootstrap} activeSeed={activeSeed} />

      <ProjectionControlPanel
        bootstrap={bootstrap}
        error={error}
        graph={graph}
        projectionResult={projectionResult}
        projectionRunning={projectionRunning}
        onRunProjection={runProjectionRefresh}
      />

      {error && !missingProjectionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <CountBadge label="Nodes" value={counts.nodes ?? counts.surface_nodes} />
        <CountBadge label="Edges" value={counts.edges ?? counts.surface_edges} />
        <CountBadge label="Deltas" value={counts.surface_deltas} />
        <CountBadge label="Pending proposals" value={counts.experience_proposals_pending} />
      </div>

      <div className="grid h-[calc(100vh-300px)] min-h-[760px] grid-cols-[270px_minmax(0,1fr)_340px] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <NodeList
          graph={graph}
          selectedNode={selectedNode}
          filterQuery={filterQuery}
          onFilterChange={setFilterQuery}
          onSelectNode={selectNode}
          onFocusNode={focusNode}
          onSaveView={saveCurrentView}
          savedViews={savedViews}
          onApplyView={applySavedView}
        />
        <div className="relative z-0 h-full min-w-0 overflow-hidden bg-gray-50">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70">
              <Loader className="animate-spin text-primary-500" size={32} />
            </div>
          )}
          <WorkbenchCanvas
            graph={graph}
            selectedNode={selectedNode}
            onSelectNode={selectNode}
            onFocusNode={focusNode}
            onCopyNodeKey={copyToClipboard}
            onFilterNodeType={(node) => setFilterQuery(`type:${node.node_type}`)}
          />
        </div>
        <div
          className="relative z-30 h-full min-w-0 overflow-hidden bg-white pointer-events-auto"
          onMouseDownCapture={(event) => event.stopPropagation()}
          onClickCapture={(event) => event.stopPropagation()}
        >
          <Inspector
            entity={entity}
            entityErrors={entityErrors}
            actions={actions}
            memory={memory}
            loading={entityLoading}
            selectedNode={selectedNode}
            actionSubmission={actionSubmission}
            actionSubmitting={actionSubmitting}
            onSubmitAction={submitSelectedAction}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
        <div>
          <div className="text-sm font-semibold text-gray-900">Details</div>
          <div className="text-xs text-gray-500">Evidence, memory, and read-model checks.</div>
        </div>
        <button
          type="button"
          onClick={() => setShowReadModelDetails((value) => !value)}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          {showReadModelDetails ? 'Hide details' : 'Show details'}
        </button>
      </div>

      {showReadModelDetails && (
        <>
          <LowerEvidencePanel
            actions={actions}
            memory={memory}
            evidencePack={evidencePack}
            selectedNode={selectedNode}
            actionSubmission={actionSubmission}
            actionSubmitting={actionSubmitting}
            onSubmitAction={submitSelectedAction}
          />
        </>
      )}
    </div>
  )
}

export default Workbench
