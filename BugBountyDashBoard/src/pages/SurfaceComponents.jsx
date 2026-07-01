import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  BarChart3,
  BrainCircuit,
  Clipboard,
  GitBranch,
  Loader,
  PlayCircle,
  RefreshCw,
  Search,
} from 'lucide-react'
import { useProgram } from '../context/ProgramContext'
import {
  getLatestSurfaceComponentAnalysis,
  getSurfaceComponentAnalysis,
  runWorkbenchProjectionRefresh,
} from '../services/api'

const signalClass = (value) => {
  if (value == null) return 'bg-slate-100 text-slate-500'
  if (value >= 75) return 'bg-slate-900 text-white'
  if (value >= 50) return 'bg-slate-700 text-white'
  if (value >= 25) return 'bg-slate-200 text-slate-800'
  return 'bg-slate-100 text-slate-600'
}

const signalValue = (signals, name) => signals?.[name] ?? null

const ScoreBadge = ({ label, value }) => (
  <div className="flex items-center justify-between gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
    <span className="text-xs font-medium text-gray-500">{label}</span>
    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${signalClass(value)}`}>
      {value == null ? 'n/a' : value}
    </span>
  </div>
)

const StatCard = ({ icon: Icon, label, value }) => (
  <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-500">{label}</span>
      <Icon className="text-primary-500" size={18} />
    </div>
    <div className="mt-2 text-2xl font-semibold text-gray-900">{value}</div>
  </div>
)

const formatDate = (value) => {
  if (!value) return 'n/a'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

const copyToClipboard = (text) => {
  if (!text) return
  navigator.clipboard.writeText(text)
}

const candidateLabel = (candidate) => {
  const capability = candidate.capability_id || 'unknown'
  const profile = candidate.profile_id || 'default'
  const signal = candidate.rank_signal
  return `${capability}/${profile}${signal == null ? '' : ` · signal ${signal}`}`
}

const isFallbackReport = (report) => String(report?.algorithm_version || report?.algorithm || '').includes('surface-local-route-family')

const projectionMode = (report) => (isFallbackReport(report) ? 'degraded fallback' : 'Neo4j/GDS materialized')

const projectionModeClass = (report) => (isFallbackReport(report)
  ? 'border-amber-200 bg-amber-50 text-amber-900'
  : 'border-green-200 bg-green-50 text-green-900')

const componentEntityKey = (report, item) => `surface-component:${report?.analysis_run_id}:${item.component_id}`

const workbenchComponentUrl = (report, item) => (
  `/workbench?lens=components&seed=${encodeURIComponent(componentEntityKey(report, item))}`
)

const signalReasons = (item, report) => {
  const signals = item.signals || {}
  const reasons = []
  if (isFallbackReport(report)) {
    reasons.push('Degraded local grouping: Neo4j/GDS was unavailable, so bridge/outlier/candidate analytics are not authoritative.')
  }
  if ((item.changed_node_count || 0) > 0) reasons.push(`${item.changed_node_count} changed nodes since previous snapshot.`)
  if ((item.action_candidates || []).length > 0) reasons.push(`${item.action_candidates.length} backend action candidate signals.`)
  if ((signals.bridge_pressure ?? 0) >= 50) reasons.push('Bridge pressure is high; inspect connector endpoints first.')
  if ((signals.outlier ?? 0) >= 50) reasons.push('Outlier signal is high; check unusual endpoints or responses.')
  if ((signals.coverage ?? 100) < 50) reasons.push('Coverage signal is low; this area may need more exploration.')
  if ((signals.exploration_pressure ?? 0) >= 75) reasons.push('Exploration pressure is high relative to other components.')
  if (!reasons.length) reasons.push('No strong graph signal exposed for this component yet.')
  return reasons.slice(0, 4)
}

const hasMetricPayload = (item, key) => {
  const payload = item?.metrics?.[key]
  return payload && typeof payload === 'object' && Object.keys(payload).length > 0
}

const graphProjectorCapabilities = (item) => ({
  profile: hasMetricPayload(item, 'profile'),
  drift: hasMetricPayload(item, 'drift'),
  bridge: hasMetricPayload(item, 'bridge'),
  outlier: hasMetricPayload(item, 'outlier'),
  coverage: hasMetricPayload(item, 'coverage'),
  candidates: (item?.action_candidates || []).length > 0,
})

const enabledCapabilities = (item) => Object.entries(graphProjectorCapabilities(item))
  .filter(([, enabled]) => enabled)
  .map(([name]) => name)

const topBySignal = (items, signalName, predicate = (value) => value != null) => [...items]
  .filter((item) => predicate(signalValue(item.signals, signalName)))
  .sort((a, b) => (signalValue(b.signals, signalName) ?? -1) - (signalValue(a.signals, signalName) ?? -1))
  .slice(0, 5)

const GraphProjectorLanes = ({ report, items }) => {
  if (!report) return null
  const fallback = isFallbackReport(report)
  const lanes = [
    { id: 'bridge', label: 'Bridge-heavy', items: topBySignal(items, 'bridge_pressure', (value) => (value ?? 0) >= 50), description: 'Connector components from graph-projector bridge analysis.' },
    { id: 'outlier', label: 'Outliers', items: topBySignal(items, 'outlier', (value) => (value ?? 0) >= 50), description: 'Unusual component neighborhoods from similarity/outlier analysis.' },
    { id: 'coverage', label: 'Low coverage', items: topBySignal(items, 'coverage', (value) => value != null && value < 60).reverse(), description: 'Components where graph-projector coverage says more exploration may help.' },
    { id: 'drift', label: 'Drift / changed', items: topBySignal(items, 'drift', (value) => (value ?? 0) > 0).concat(items.filter((item) => (item.changed_node_count || 0) > 0)).slice(0, 5), description: 'Components with drift score or changed nodes.' },
    { id: 'candidates', label: 'Action candidates', items: [...items].filter((item) => (item.action_candidates || []).length > 0).slice(0, 5), description: 'Backend materialized candidate action signals.' },
  ]
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Graph-projector lanes</h2>
          <p className="mt-1 text-sm text-gray-500">These buckets expose what Neo4j/GDS materialized for triage: bridges, outliers, coverage, drift, and candidate actions.</p>
        </div>
        {fallback && <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">degraded: GDS lanes unavailable</span>}
      </div>
      <div className="mt-4 grid gap-3 xl:grid-cols-5 md:grid-cols-2">
        {lanes.map((lane) => (
          <section key={lane.id} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold text-gray-900">{lane.label}</div>
              <span className="rounded bg-white px-2 py-0.5 text-xs text-gray-600">{fallback ? 'n/a' : lane.items.length}</span>
            </div>
            <p className="mt-1 min-h-[32px] text-xs text-gray-500">{fallback ? 'Neo4j/GDS was not available for this report.' : lane.description}</p>
            <div className="mt-3 space-y-2">
              {!fallback && lane.items.length > 0 ? lane.items.map((item) => (
                <Link
                  key={`${lane.id}-${item.component_id}`}
                  to={workbenchComponentUrl(report, item)}
                  className="block rounded border border-gray-200 bg-white px-2 py-1.5 text-xs hover:border-primary-200 hover:bg-primary-50"
                >
                  <div className="font-semibold text-gray-800">Component {item.component_id}</div>
                  <div className="mt-0.5 text-gray-500">{item.node_count} nodes · signal {signalValue(item.signals, lane.id === 'bridge' ? 'bridge_pressure' : lane.id === 'candidates' ? 'exploration_pressure' : lane.id) ?? 'n/a'}</div>
                </Link>
              )) : (
                <div className="rounded border border-dashed border-gray-200 bg-white px-2 py-2 text-xs text-gray-400">No lane items</div>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

const ComponentSignalPayloads = ({ item, report }) => {
  const capabilities = enabledCapabilities(item)
  const fallback = isFallbackReport(report)
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Materialized graph-projector data</div>
      {fallback ? (
        <p className="mt-2 text-sm text-amber-800">Fallback grouping only. Neo4j/GDS profile, bridge, outlier, coverage, drift and candidate payloads are not authoritative here.</p>
      ) : capabilities.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {capabilities.map((capability) => (
            <span key={capability} className="rounded bg-white px-2 py-1 text-xs font-semibold text-purple-700 shadow-sm">{capability}</span>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-sm text-gray-500">No graph-projector payloads were materialized for this component.</p>
      )}
    </div>
  )
}

const GraphProjectionBanner = ({ report, boundary }) => {
  if (!report) return null
  const fallback = isFallbackReport(report)
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${projectionModeClass(report)}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Projection source: {projectionMode(report)}</div>
          <p className="mt-1 max-w-4xl text-sm">
            {fallback
              ? 'Neo4j/GDS component analytics were unavailable. This page is showing degraded Surface Map route-family groups, not full graph-projector math.'
              : 'This analysis was materialized from graph-projector output. Use it to open component subgraphs, inspect bridge/outlier/coverage signals, and review backend action candidate signals.'}
          </p>
        </div>
        <span className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold">
          {boundary?.signal_contract?.calibration_status || 'uncalibrated'}
        </span>
      </div>
    </div>
  )
}

const ComponentCard = ({ item, report }) => {
  const candidates = item.action_candidates || []
  const signals = item.signals || {}
  const exploration = signalValue(signals, 'exploration_pressure')
  const fallback = isFallbackReport(report)
  const reasons = signalReasons(item, report)
  return (
    <div className={`rounded-xl border bg-white p-5 shadow-sm ${fallback ? 'border-amber-200' : 'border-gray-200'}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-gray-900">Component {item.component_id}</h3>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{item.node_count} nodes</span>
            <span className="rounded bg-primary-50 px-2 py-0.5 text-xs text-primary-700">{item.changed_node_count} changed</span>
            <span className={`rounded px-2 py-0.5 text-xs font-semibold ${fallback ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
              {fallback ? 'fallback grouping' : 'Neo4j/GDS'}
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            Graph-projector component profile. Signals are for triage and drilldown; they are not vulnerability verdicts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded px-3 py-1 text-sm font-semibold ${signalClass(exploration)}`}>signal {exploration ?? 'n/a'}</span>
          <Link
            to={workbenchComponentUrl(report, item)}
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800"
          >
            Open in Workbench
          </Link>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Why inspect this component</div>
          <ul className="mt-2 space-y-1 text-sm text-gray-700">
            {reasons.map((reason) => <li key={reason}>• {reason}</li>)}
          </ul>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <ScoreBadge label="Bridge pressure" value={signalValue(signals, 'bridge_pressure')} />
          <ScoreBadge label="Outlier" value={signalValue(signals, 'outlier')} />
          <ScoreBadge label="Coverage" value={signalValue(signals, 'coverage')} />
          <ScoreBadge label="Exploration pressure" value={exploration} />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <ScoreBadge label="Structural pressure" value={signalValue(signals, 'structural_pressure')} />
        <ScoreBadge label="Drift" value={signalValue(signals, 'drift')} />
      </div>

      <div className="mt-4">
        <ComponentSignalPayloads item={item} report={report} />
      </div>

      {candidates.length > 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Backend action candidate signals</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {candidates.slice(0, 8).map((candidate, index) => (
              <span key={`${item.component_id}-candidate-${index}`} className="rounded bg-white px-2 py-1 text-xs text-gray-700 shadow-sm">
                {candidateLabel(candidate)}
              </span>
            ))}
            {candidates.length > 8 && <span className="rounded px-2 py-1 text-xs text-gray-500">+{candidates.length - 8}</span>}
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
          No materialized action candidates. {fallback ? 'Expected in fallback mode.' : 'Check graph-projector candidate generation.'}
        </div>
      )}
    </div>
  )
}

const SurfaceComponents = () => {
  const { selectedProgram } = useProgram()
  const [snapshotId, setSnapshotId] = useState('')
  const [previousSnapshotId, setPreviousSnapshotId] = useState('')
  const [report, setReport] = useState(null)
  const [boundary, setBoundary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [materializing, setMaterializing] = useState(false)
  const [projectionResult, setProjectionResult] = useState(null)
  const [error, setError] = useState(null)

  const items = report?.items || []
  const sortedItems = useMemo(
    () => [...items].sort((a, b) => (
      signalValue(b.signals, 'exploration_pressure') ?? -1
    ) - (
      signalValue(a.signals, 'exploration_pressure') ?? -1
    )),
    [items],
  )

  const loadLatest = useCallback(async () => {
    if (!selectedProgram) return
    setLoading(true)
    setError(null)
    try {
      const response = await getLatestSurfaceComponentAnalysis(selectedProgram.id)
      setReport(response.data.analysis)
      setBoundary(response.data.boundary)
      setSnapshotId(response.data.analysis?.snapshot_id || '')
      setPreviousSnapshotId(response.data.analysis?.previous_snapshot_id || '')
    } catch (err) {
      setReport(null)
      setBoundary(null)
      setError(err.response?.data?.detail || err.message || 'Failed to load surface component analysis')
    } finally {
      setLoading(false)
    }
  }, [selectedProgram])

  const loadSnapshot = async (event) => {
    event.preventDefault()
    if (!selectedProgram || !snapshotId.trim()) return
    setLoading(true)
    setError(null)
    try {
      const response = await getSurfaceComponentAnalysis({
        programId: selectedProgram.id,
        snapshotId: snapshotId.trim(),
        previousSnapshotId: previousSnapshotId.trim() || undefined,
      })
      setReport(response.data.analysis)
      setBoundary(response.data.boundary)
    } catch (err) {
      setReport(null)
      setBoundary(null)
      setError(err.response?.data?.detail || err.message || 'Failed to load surface component analysis')
    } finally {
      setLoading(false)
    }
  }

  const materializeLatest = async (operation = 'materialize_components') => {
    if (!selectedProgram) return
    setMaterializing(true)
    setProjectionResult(null)
    setError(null)
    try {
      const response = await runWorkbenchProjectionRefresh({
        program_id: selectedProgram.id,
        operation,
      })
      setProjectionResult(response.data)
      await loadLatest()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to materialize surface component analysis')
    } finally {
      setMaterializing(false)
    }
  }

  useEffect(() => {
    if (selectedProgram) {
      loadLatest()
    }
  }, [selectedProgram, loadLatest])

  if (!selectedProgram) {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-6">
        <div className="flex items-center space-x-3">
          <AlertCircle className="text-yellow-600" size={24} />
          <div>
            <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
            <p className="mt-1 text-sm text-yellow-700">
              Select a program to view persisted surface component analysis.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Surface Components</h1>
          <p className="mt-2 text-gray-600">
            Persisted graph-math read model for{' '}
            <span className="font-semibold text-primary-600">{selectedProgram.name}</span>
          </p>
        </div>
        <button
          onClick={loadLatest}
          disabled={loading}
          className="flex items-center space-x-2 rounded-lg bg-primary-600 px-4 py-2 text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {loading ? <Loader className="animate-spin" size={16} /> : <RefreshCw size={16} />}
          <span>Latest</span>
        </button>
      </div>

      <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-blue-950">
              <PlayCircle size={16} />
              Component data setup
            </div>
            <p className="mt-1 max-w-3xl text-sm text-blue-800">
              Build component analysis from the latest Surface Map snapshot. The backend resolves snapshot ids; this page should not make you paste UUIDs or run graph-projector commands.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => materializeLatest('materialize_components')}
              disabled={materializing}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {materializing ? <Loader className="animate-spin" size={16} /> : <PlayCircle size={16} />}
              <span>Materialize latest components</span>
            </button>
            <button
              type="button"
              onClick={() => materializeLatest('refresh_workbench')}
              disabled={materializing}
              className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm font-medium text-blue-800 hover:bg-blue-100 disabled:opacity-50"
            >
              {materializing ? <Loader className="animate-spin" size={16} /> : <RefreshCw size={16} />}
              <span>Build surface + components</span>
            </button>
          </div>
        </div>

        {projectionResult && (
          <div className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-xs text-blue-900">
            <div className="font-semibold">{projectionResult.status}: {projectionResult.message}</div>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              {(projectionResult.steps || []).map((step) => (
                <div key={step.step_id} className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                  <div className="font-semibold text-gray-900">{step.step_id} · {step.status}</div>
                  <div className="mt-1 text-gray-600">{step.message}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <details className="mt-4 rounded-lg border border-blue-100 bg-white p-3">
          <summary className="cursor-pointer text-xs font-semibold text-blue-900">Advanced: load a specific snapshot by UUID</summary>
          <form onSubmit={loadSnapshot} className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Snapshot ID</span>
              <input
                value={snapshotId}
                onChange={(event) => setSnapshotId(event.target.value)}
                placeholder="current snapshot UUID"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Previous Snapshot ID</span>
              <input
                value={previousSnapshotId}
                onChange={(event) => setPreviousSnapshotId(event.target.value)}
                placeholder="optional previous snapshot UUID"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </label>
            <div className="flex items-end gap-2">
              <button
                type="submit"
                disabled={loading || !snapshotId.trim()}
                className="flex items-center space-x-2 rounded-lg bg-gray-900 px-4 py-2 text-white hover:bg-gray-800 disabled:opacity-50"
              >
                <Search size={16} />
                <span>Load snapshot</span>
              </button>
              {report?.snapshot_id && (
                <button
                  type="button"
                  onClick={() => copyToClipboard(report.snapshot_id)}
                  className="rounded-lg border border-gray-300 p-2 text-gray-600 hover:bg-gray-50"
                  title="Copy snapshot id"
                >
                  <Clipboard size={16} />
                </button>
              )}
            </div>
          </form>
        </details>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <div className="font-semibold">Component analysis is not ready.</div>
          <div className="mt-1">{error}</div>
          <div className="mt-2 text-xs">Use the setup buttons above; snapshot ids are resolved by the backend.</div>
        </div>
      )}

      {loading && !report && (
        <div className="flex h-64 items-center justify-center">
          <Loader className="animate-spin text-primary-500" size={32} />
        </div>
      )}

      {report && (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <StatCard icon={GitBranch} label="Components" value={report.item_count} />
            <StatCard icon={BarChart3} label="Algorithm" value={report.algorithm_version} />
            <StatCard icon={BrainCircuit} label="Created" value={formatDate(report.created_at)} />
            <StatCard icon={Search} label="Signal kind" value={boundary?.signal_contract?.kind || 'heuristic'} />
          </div>

          <GraphProjectionBanner report={report} boundary={boundary} />

          <GraphProjectorLanes report={report} items={items} />

          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
              <div>
                <span className="font-medium text-gray-500">Snapshot:</span>{' '}
                <span className="font-mono text-xs text-gray-700">{report.snapshot_id}</span>
              </div>
              <div>
                <span className="font-medium text-gray-500">Previous:</span>{' '}
                <span className="font-mono text-xs text-gray-700">{report.previous_snapshot_id || 'none'}</span>
              </div>
              <div>
                <span className="font-medium text-gray-500">Run:</span>{' '}
                <span className="font-mono text-xs text-gray-700">{report.analysis_run_id}</span>
              </div>
              <div>
                <span className="font-medium text-gray-500">Calibration:</span>{' '}
                <span className="font-mono text-xs text-gray-700">
                  {boundary?.signal_contract?.calibration_status || 'uncalibrated'}
                </span>
              </div>
              <div className="md:col-span-2">
                <span className="font-medium text-gray-500">Fingerprint:</span>{' '}
                <span className="font-mono text-xs text-gray-700">{report.report_fingerprint}</span>
              </div>
            </div>
          </div>

          {sortedItems.length === 0 ? (
            <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-12 text-center">
              <p className="text-gray-500">No materialized component items found.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {sortedItems.map((item) => (
                <ComponentCard key={item.component_id} item={item} report={report} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default SurfaceComponents
