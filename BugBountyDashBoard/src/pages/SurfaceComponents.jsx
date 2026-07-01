import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  BarChart3,
  BrainCircuit,
  Clipboard,
  GitBranch,
  Loader,
  RefreshCw,
  Search,
} from 'lucide-react'
import { useProgram } from '../context/ProgramContext'
import {
  getLatestSurfaceComponentAnalysis,
  getSurfaceComponentAnalysis,
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

const ComponentCard = ({ item }) => {
  const candidates = item.action_candidates || []
  const signals = item.signals || {}
  const exploration = signalValue(signals, 'exploration_pressure')
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-gray-900">Component {item.component_id}</h3>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
              {item.node_count} nodes
            </span>
            <span className="rounded bg-primary-50 px-2 py-0.5 text-xs text-primary-700">
              {item.changed_node_count} changed
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            Materialized surface component profile. Values are uncalibrated heuristic graph signals, not priority, risk, severity, or learned utility.
          </p>
        </div>
        <span className={`rounded px-3 py-1 text-sm font-semibold ${signalClass(exploration)}`}>
          signal {exploration ?? 'n/a'}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
        <ScoreBadge label="Structural pressure" value={signalValue(signals, 'structural_pressure')} />
        <ScoreBadge label="Drift" value={signalValue(signals, 'drift')} />
        <ScoreBadge label="Bridge pressure" value={signalValue(signals, 'bridge_pressure')} />
        <ScoreBadge label="Outlier" value={signalValue(signals, 'outlier')} />
        <ScoreBadge label="Coverage" value={signalValue(signals, 'coverage')} />
        <ScoreBadge label="Exploration pressure" value={exploration} />
      </div>

      {candidates.length > 0 && (
        <div className="mt-4 rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Action candidate signals
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {candidates.slice(0, 6).map((candidate, index) => (
              <span key={`${item.component_id}-candidate-${index}`} className="rounded bg-white px-2 py-1 text-xs text-gray-700 shadow-sm">
                {candidateLabel(candidate)}
              </span>
            ))}
            {candidates.length > 6 && (
              <span className="rounded px-2 py-1 text-xs text-gray-500">+{candidates.length - 6}</span>
            )}
          </div>
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

      <form onSubmit={loadSnapshot} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
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
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
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
                <ComponentCard key={item.component_id} item={item} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default SurfaceComponents
