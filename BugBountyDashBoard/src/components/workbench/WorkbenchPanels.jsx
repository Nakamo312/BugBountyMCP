import React, { useMemo, useState } from 'react'
import {
  Boxes,
  CheckCircle2,
  AlertCircle,
  Clipboard,
  Command,
  DatabaseZap,
  Filter,
  Save,
  Search,
  Loader,
  PlayCircle,
  Target,
  X,
} from 'lucide-react'

export const copyToClipboard = (value) => {
  if (!value) return
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(value).catch(() => {})
    return
  }
  if (typeof document === 'undefined') return
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    document.execCommand('copy')
  } catch (_) {
    // Clipboard fallback is best effort only; copy failures must not break the workbench.
  } finally {
    document.body.removeChild(textarea)
  }
}

const savedViewsStorageKey = (programId) => `bb.workbench.savedViews.${programId}`

export const loadSavedViews = (programId) => {
  if (!programId || typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(savedViewsStorageKey(programId))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.slice(0, 8) : []
  } catch (_) {
    return []
  }
}

export const persistSavedViews = (programId, views) => {
  if (!programId || typeof window === 'undefined') return
  try {
    window.localStorage.setItem(savedViewsStorageKey(programId), JSON.stringify(views.slice(0, 8)))
  } catch (_) {
    // Local persistence is convenience state; storage failures should not block graph work.
  }
}

export const emptyCounts = {}

export const CountBadge = ({ label, value }) => (
  <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-sm">
    <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500">{label}</div>
    <div className="mt-0.5 text-lg font-semibold text-gray-900">{value ?? 0}</div>
  </div>
)

export const LensSelector = ({ lens, lenses, onChange }) => (
  <div className="flex flex-wrap gap-2">
    {lenses.map((item) => (
      <button
        key={item.lens}
        type="button"
        disabled={!item.available}
        onClick={() => onChange(item.lens)}
        title={item.reason || item.label}
        className={`rounded-lg border px-3 py-2 text-sm font-medium ${
          lens === item.lens
            ? 'border-primary-600 bg-primary-600 text-white'
            : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-45'
        }`}
      >
        {item.label}
      </button>
    ))}
  </div>
)

const filterTokens = (value) => value.toLowerCase().split(/\s+/).map((token) => token.trim()).filter(Boolean)

const tokenMatchesNode = (token, node) => {
  if (token === 'stale') return node.staleness === 'stale'
  if (token === 'fresh') return node.staleness === 'fresh'
  if (token === 'unknown') return node.staleness === 'unknown'
  if (token === 'gap') return String(node.node_type || '').includes('gap') || (node.badges || []).includes('gap')
  if (token === 'checked') return (node.badges || []).includes('checked')
  if (token === 'changed') return (node.badges || []).includes('changed') || node.properties?.delta_state === 'changed'
  if (token === 'has:evidence') return (node.evidence_refs || []).length > 0
  if (token === 'has:actions') return (node.action_affordance_count || 0) > 0
  if (token.startsWith('type:')) return String(node.node_type || '').toLowerCase() === token.slice(5)
  if (token.startsWith('badge:')) return (node.badges || []).some((badge) => String(badge).toLowerCase() === token.slice(6))
  const haystack = [
    node.id,
    node.entity_key,
    node.node_type,
    node.label,
    node.caption,
    ...(node.badges || []),
  ].join(' ').toLowerCase()
  return haystack.includes(token)
}

const filteredNodes = (graph, query) => {
  const nodes = graph?.nodes || []
  const tokens = filterTokens(query)
  if (!tokens.length) return nodes
  return nodes.filter((node) => tokens.every((token) => tokenMatchesNode(token, node)))
}

const SavedViews = ({ views, onApplyView, onSaveView }) => (
  <section className="border-t border-gray-200 pt-3">
    <div className="mb-2 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
        <Save size={15} />
        Saved views
      </div>
      <button
        type="button"
        onClick={onSaveView}
        className="rounded border border-gray-200 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
      >
        Save
      </button>
    </div>
    {views.length === 0 ? (
      <p className="text-xs text-gray-500">Saved views persist locally per program: lens, filter, selected seed.</p>
    ) : (
      <div className="space-y-1">
        {views.map((view) => (
          <button
            key={view.id}
            type="button"
            onClick={() => onApplyView(view)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-left text-xs hover:bg-gray-50"
            title={view.seed || view.filter || view.lens}
          >
            <div className="font-semibold text-gray-800">{view.label}</div>
            <div className="mt-0.5 truncate text-gray-500">{view.lens}{view.filter ? ` · ${view.filter}` : ''}</div>
          </button>
        ))}
      </div>
    )}
  </section>
)

export const NodeList = ({ graph, selectedNode, filterQuery, onFilterChange, onSelectNode, onFocusNode, onSaveView, savedViews, onApplyView }) => {
  const nodes = useMemo(() => filteredNodes(graph, filterQuery), [graph, filterQuery])
  const total = graph?.nodes?.length || 0
  return (
    <aside className="h-full overflow-y-auto border-r border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
          <Boxes size={16} />
          Entities
        </div>
        <span className="text-xs text-gray-500">{nodes.length}/{total}</span>
      </div>

      <div className="mb-3 space-y-2">
        <label className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
          <Filter size={15} className="text-gray-500" />
          <input
            value={filterQuery}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder="filter, type:endpoint, gap, stale, has:actions"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400"
          />
          {filterQuery && (
            <button type="button" onClick={() => onFilterChange('')} className="text-gray-400 hover:text-gray-700">
              <X size={14} />
            </button>
          )}
        </label>
      </div>

      <div className="space-y-2">
        {nodes.map((node) => (
          <div
            key={node.id}
            className={`rounded-lg border ${
              selectedNode?.entity_key === node.entity_key ? 'border-primary-500 bg-primary-50' : 'border-gray-200 bg-white'
            }`}
          >
            <button
              type="button"
              onClick={() => onSelectNode(node)}
              className="w-full p-3 text-left hover:bg-gray-50"
            >
              <div className="truncate text-sm font-semibold text-gray-900" title={node.label}>{node.label}</div>
              <div className="mt-1 truncate text-xs text-gray-500" title={node.entity_key}>{node.node_type}</div>
            </button>
            <div className="flex items-center justify-between border-t border-gray-100 px-3 py-2 text-xs text-gray-500">
              <span>{node.staleness || 'unknown'}</span>
              <button
                type="button"
                onClick={() => onFocusNode(node)}
                className="flex items-center gap-1 font-medium text-primary-600 hover:text-primary-700"
                title="Reload this lens around this entity as seed"
              >
                <Target size={13} />
                Focus
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4">
        <SavedViews views={savedViews} onApplyView={onApplyView} onSaveView={onSaveView} />
      </div>
    </aside>
  )
}

export const ProjectionStatus = ({ bootstrap, activeSeed }) => {
  const queueHealth = bootstrap?.queue_health || emptyCounts
  const freshness = bootstrap?.projection_freshness || emptyCounts
  const queueEntries = Object.entries(queueHealth).filter(([, value]) => value && typeof value === 'object')
  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_1.5fr]">
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
          <DatabaseZap size={16} />
          Projection status
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <span className="rounded bg-gray-50 px-2 py-1 text-gray-600">surface analysis: {String(freshness.surface_analysis_fresh ?? 'unknown')}</span>
          <span className="rounded bg-gray-50 px-2 py-1 text-gray-600">search index: {String(freshness.search_index_fresh ?? 'unknown')}</span>
          <span className="rounded bg-gray-50 px-2 py-1 text-gray-600">ui data: {String(freshness.ui_data_fresh ?? 'unknown')}</span>
          <span className="rounded bg-gray-50 px-2 py-1 text-gray-600">seed: {activeSeed || 'none'}</span>
        </div>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="text-sm font-semibold text-gray-900">Queue health</div>
        {queueEntries.length === 0 ? (
          <p className="mt-2 text-sm text-gray-500">No queue state exposed by bootstrap.</p>
        ) : (
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {queueEntries.map(([name, stats]) => (
              <div key={name} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                <div className="truncate text-xs font-semibold text-gray-700" title={name}>{name}</div>
                <div className="mt-1 text-[11px] text-gray-500">
                  p:{stats.pending || 0} l:{stats.locked || 0} f:{stats.failed || 0}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export const CommandBar = ({ retrieveQuery, setRetrieveQuery, onRerunSelected, selectedNode }) => (
  <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex min-w-[280px] flex-1 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
        <Command size={16} className="text-gray-500" />
        <input
          value={retrieveQuery}
          onChange={(event) => setRetrieveQuery(event.target.value)}
          placeholder="retrieve query for selected entity, not a prompt blob"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400"
        />
        {retrieveQuery && (
          <button type="button" onClick={() => setRetrieveQuery('')} className="text-gray-400 hover:text-gray-700">
            <X size={14} />
          </button>
        )}
      </div>
      <button
        type="button"
        disabled={!selectedNode}
        onClick={onRerunSelected}
        className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-45"
      >
        Re-rank evidence
      </button>
    </div>
    <p className="mt-2 text-xs text-gray-500">
      This bar only affects read-side retrieval ranking for the selected entity. It does not submit actions or assemble prompts.
    </p>
  </div>
)

const JsonBlock = ({ value }) => (
  <pre className="max-h-44 overflow-auto rounded-lg bg-gray-950 p-3 text-xs text-gray-100">
    {JSON.stringify(value || {}, null, 2)}
  </pre>
)

const SmallMetric = ({ label, value }) => (
  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
    <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500">{label}</div>
    <div className="mt-0.5 text-sm font-semibold text-gray-900">{value ?? 0}</div>
  </div>
)

export const LowerEvidencePanel = ({ actions, memory, evidencePack, selectedNode }) => {
  const affordances = actions?.actions || []
  const rankedContext = evidencePack?.ranked_context || []
  const fragments = rankedContext.length
    ? rankedContext.map((item) => ({ ...item.fragment, rank: item.rank, rank_score: item.score, rank_reasons: item.reasons }))
    : evidencePack?.fragments || memory?.fragments || []
  const summary = memory?.summaries?.[0] || {}
  const searchRefs = evidencePack?.search_projection_refs || []
  const graphSummary = evidencePack?.graph_context_summary || {}

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
          <Search size={16} />
          Evidence timeline / memory tree / action run log / delta panel
        </div>
        <div className="text-xs text-gray-500">
          {selectedNode ? selectedNode.entity_key : 'No entity selected'}
        </div>
      </div>

      {!selectedNode ? (
        <p className="mt-3 text-sm text-gray-500">Select an entity to load read-only evidence, prior outcomes, and backend action affordances.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_1fr_1fr]">
          <section className="space-y-3">
            <div className="text-sm font-semibold text-gray-900">Retrieved context / Recent memory fragments</div>
            {graphSummary.available && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
                graph context: {graphSummary.node_count || 0} nodes · {graphSummary.edge_count || 0} edges · {graphSummary.neighbor_count || 0} neighbors
              </div>
            )}
            {searchRefs.length > 0 && (
              <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
                {searchRefs.length} search projection references are linked to this pack.
              </div>
            )}
            {fragments.length === 0 ? (
              <p className="text-sm text-gray-500">No action outcomes or evidence fragments are linked to this entity yet.</p>
            ) : (
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {fragments.slice(0, 10).map((fragment, index) => (
                  <div key={fragment.id || fragment.outcome_id || fragment.run_id || index} className="rounded-lg border border-gray-200 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-gray-900">{fragment.capability_id || fragment.kind}</div>
                      <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                        {fragment.rank ? `#${fragment.rank} · ${fragment.rank_score}` : fragment.terminal_outcome || fragment.status}
                      </span>
                    </div>
                    <div className="mt-1 truncate text-xs text-gray-500" title={fragment.entity_key}>{fragment.entity_key}</div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-600">
                      <span>nodes: {fragment.delta?.surface_nodes ?? 0}</span>
                      <span>edges: {fragment.delta?.surface_edges ?? 0}</span>
                      <span>gain: {fragment.score?.information_gain ?? 0}</span>
                    </div>
                    {fragment.rank_reasons?.length > 0 && (
                      <div className="mt-2 text-xs text-gray-500">{fragment.rank_reasons.join(', ')}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <div className="text-sm font-semibold text-gray-900">Delta summary</div>
            <div className="grid grid-cols-2 gap-2">
              <SmallMetric label="Outcomes" value={summary.outcome_count} />
              <SmallMetric label="Artifacts" value={summary.artifact_count} />
              <SmallMetric label="New nodes" value={summary.new_surface_nodes_total} />
              <SmallMetric label="New deltas" value={summary.new_surface_deltas_total} />
            </div>
            <div className="text-xs text-gray-500">
              Summaries are pointers over fragments, not truth. They can be rebuilt from action outcomes and evidence references.
            </div>
          </section>

          <section className="space-y-3">
            <div className="text-sm font-semibold text-gray-900">Backend action affordances</div>
            {affordances.length === 0 ? (
              <p className="text-sm text-gray-500">No matching prior or queued actions are exposed for this entity.</p>
            ) : (
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {affordances.slice(0, 8).map((action) => (
                  <div key={action.policy_preview?.action_id || action.catalog_id} className="rounded-lg border border-gray-200 p-3">
                    <div className="text-sm font-semibold text-gray-900">{action.label}</div>
                    <div className="mt-1 text-xs text-gray-500">{action.catalog_id} · {action.enabled ? 'enabled' : action.disabled_reasons.join(', ') || 'disabled'}</div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}


const groupedActionAffordances = (affordances) => ({
  enabled: affordances.filter((action) => action.enabled),
  blocked: affordances.filter((action) => !action.enabled),
})

const ActionAffordanceList = ({ affordances }) => {
  const groups = groupedActionAffordances(affordances)
  if (affordances.length === 0) {
    return <p className="text-sm text-gray-500">No executable affordances are exposed by the backend for this entity yet.</p>
  }
  return (
    <div className="space-y-3">
      {groups.enabled.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-green-700">Enabled by backend</div>
          {groups.enabled.map((action, index) => (
            <div key={`${action.catalog_id}-enabled-${index}`} className="rounded-lg border border-green-100 bg-green-50 p-3">
              <div className="text-sm font-semibold text-gray-900">{action.label}</div>
              <div className="mt-1 text-xs text-gray-600">{action.catalog_id} · {action.profile}</div>
            </div>
          ))}
        </div>
      )}
      {groups.blocked.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-orange-700">Blocked or read-only</div>
          {groups.blocked.map((action, index) => (
            <div key={`${action.catalog_id}-blocked-${index}`} className="rounded-lg border border-orange-100 bg-orange-50 p-3">
              <div className="text-sm font-semibold text-gray-900">{action.label}</div>
              <div className="mt-1 text-xs text-gray-600">{action.catalog_id} · {(action.disabled_reasons || []).join(', ') || 'disabled'}</div>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-gray-500">Affordances are backend read-side state. This inspector does not submit actions.</p>
    </div>
  )
}

export const InspectorTabs = ({ activeSection, sections, onChange }) => (
  <div className="mt-5 flex flex-wrap gap-2 border-b border-gray-200 pb-3">
    {sections.map((section) => (
      <button
        key={section.id}
        type="button"
        onClick={() => onChange(section.id)}
        className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
          activeSection === section.id
            ? 'bg-primary-600 text-white'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        }`}
      >
        {section.label}{section.count !== undefined ? ` · ${section.count}` : ''}
      </button>
    ))}
  </div>
)

export const Inspector = ({ entity, actions, memory, loading, selectedNode }) => {
  const [activeSection, setActiveSection] = useState('profile')
  const affordances = actions?.actions || []
  const fragments = memory?.fragments || []
  const evidenceRefs = entity?.evidence_refs || []
  const sections = [
    { id: 'profile', label: 'Profile' },
    { id: 'evidence', label: 'Evidence', count: evidenceRefs.length },
    { id: 'actions', label: 'Actions', count: affordances.length },
    { id: 'memory', label: 'Memory', count: fragments.length },
  ]

  if (!selectedNode) {
    return (
      <aside className="h-full border-l border-gray-200 bg-white p-5">
        <div className="text-sm font-semibold text-gray-900">Inspector</div>
        <p className="mt-2 text-sm text-gray-500">Select a graph node to read profile, evidence, memory pointers, and backend action affordances.</p>
      </aside>
    )
  }

  if (loading) {
    return (
      <aside className="flex h-full items-center justify-center border-l border-gray-200 bg-white">
        <Loader className="animate-spin text-primary-500" size={28} />
      </aside>
    )
  }

  return (
    <aside className="h-full overflow-y-auto border-l border-gray-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Inspector</div>
          <h2 className="mt-1 text-lg font-semibold text-gray-900">{entity?.profile?.label || selectedNode.label}</h2>
          <p className="mt-1 text-xs text-gray-500">{entity?.entity_key || selectedNode.entity_key}</p>
        </div>
        <button
          type="button"
          onClick={() => copyToClipboard(entity?.entity_key || selectedNode.entity_key)}
          className="rounded-lg border border-gray-300 p-2 text-gray-600 hover:bg-gray-50"
          title="Copy entity key"
        >
          <Clipboard size={16} />
        </button>
      </div>

      <InspectorTabs activeSection={activeSection} sections={sections} onChange={setActiveSection} />

      {activeSection === 'profile' && (
        <section className="mt-5 space-y-2">
          <div className="text-sm font-semibold text-gray-900">Profile</div>
          <JsonBlock value={entity?.profile} />
        </section>
      )}

      {activeSection === 'evidence' && (
        <section className="mt-5 space-y-2">
          <div className="text-sm font-semibold text-gray-900">Evidence</div>
          {evidenceRefs.length === 0 ? (
            <p className="text-sm text-gray-500">No evidence refs exposed for this entity.</p>
          ) : (
            <div className="space-y-2">
              {evidenceRefs.map((ref, index) => (
                <div key={`${ref.type}-${ref.id}-${index}`} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700">
                  {ref.type}: <span className="font-mono">{ref.id}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {activeSection === 'actions' && (
        <section className="mt-5 space-y-2">
          <div className="text-sm font-semibold text-gray-900">Action affordances</div>
          <ActionAffordanceList affordances={affordances} />
        </section>
      )}

      {activeSection === 'memory' && (
        <section className="mt-5 space-y-2">
          <div className="text-sm font-semibold text-gray-900">Memory</div>
          {fragments.length === 0 ? (
            <p className="text-sm text-gray-500">Memory fragments are not materialized for this entity yet.</p>
          ) : (
            <JsonBlock value={fragments} />
          )}
        </section>
      )}
    </aside>
  )
}


const hasDeltaSignal = (memory, evidencePack) => {
  const summaries = memory?.summaries || []
  const fragments = evidencePack?.fragments || memory?.fragments || []
  const ranked = evidencePack?.ranked_context || []
  return summaries.some((summary) => (summary.new_surface_deltas_total || summary.new_surface_nodes_total || 0) > 0)
    || fragments.some((fragment) => (fragment.delta?.surface_nodes || fragment.delta?.surface_edges || fragment.delta?.surface_deltas || 0) > 0)
    || ranked.some((item) => item.reasons?.includes('delta_signal'))
}

const workbenchAnswerChecks = ({ entity, actions, memory, evidencePack, selectedNode }) => {
  const profile = entity?.profile || {}
  const affordances = actions?.actions || []
  const evidenceRefs = entity?.evidence_refs || evidencePack?.evidence_refs || []
  const fragments = memory?.fragments || evidencePack?.fragments || []
  const rankedContext = evidencePack?.ranked_context || []
  const summaries = memory?.summaries || []
  return [
    { label: 'What is this entity?', passed: Boolean(selectedNode || profile.label || entity?.entity_key) },
    { label: 'Where did it come from?', passed: Boolean(evidenceRefs.length || selectedNode?.source_refs?.length || profile.source_projection) },
    { label: 'What changed recently?', passed: hasDeltaSignal(memory, evidencePack) },
    { label: 'What evidence supports it?', passed: Boolean(evidenceRefs.length || rankedContext.length) },
    { label: 'What actions were already tried?', passed: Boolean((entity?.related_actions || []).length || summaries.some((summary) => summary.outcome_count > 0)) },
    { label: 'Which actions are available now?', passed: affordances.some((action) => action.enabled) },
    { label: 'Which actions are blocked and why?', passed: affordances.some((action) => !action.enabled && (action.disabled_reasons || []).length) },
    { label: 'Which related hypotheses exist?', passed: Boolean((entity?.related_hypotheses || []).length || String(selectedNode?.node_type || '').includes('hypothesis')) },
    { label: 'Which memory explains the state?', passed: Boolean(fragments.length || summaries.length || evidencePack?.entity_summaries?.length) },
    { label: 'What delta appeared after the last action?', passed: hasDeltaSignal(memory, evidencePack) },
  ]
}

export const WorkbenchAnswerCoverage = ({ entity, actions, memory, evidencePack, selectedNode }) => {
  const checks = workbenchAnswerChecks({ entity, actions, memory, evidencePack, selectedNode })
  const passed = checks.filter((item) => item.passed).length
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
          <CheckCircle2 size={16} />
          Workbench answer coverage
        </div>
        <div className="text-xs font-semibold text-gray-600">{passed}/{checks.length}</div>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        {checks.map((item) => (
          <div
            key={item.label}
            className={`rounded-lg border px-3 py-2 text-xs ${item.passed ? 'border-green-100 bg-green-50 text-green-700' : 'border-gray-200 bg-gray-50 text-gray-500'}`}
          >
            {item.label}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-gray-500">
        This checklist is computed from loaded read models. It is not a vulnerability verdict or confidence score.
      </p>
    </div>
  )
}


export const ProjectionControlPanel = ({
  bootstrap,
  error,
  graph,
  projectionResult,
  projectionRunning,
  onRunProjection,
}) => {
  const freshness = bootstrap?.projection_freshness || {}
  const hasSnapshot = Boolean(freshness.latest_surface_snapshot)
  const hasAnalysis = Boolean(freshness.latest_surface_analysis)
  const graphEmpty = !graph || (graph.nodes || []).length === 0
  const needsSurface = graphEmpty || !hasSnapshot || String(error || '').includes('surface graph not found')
  const needsComponents = hasSnapshot && !hasAnalysis

  if (!needsSurface && !needsComponents && !projectionResult) return null

  const primaryOperation = needsSurface ? 'build_surface' : 'materialize_components'
  const primaryLabel = needsSurface ? 'Build surface map' : 'Materialize components'
  const primaryHint = needsSurface
    ? 'Build a Surface Map snapshot from stored observations. No snapshot id or docker command required.'
    : 'Build materialized component analysis from the latest surface snapshot. Snapshot id is resolved by backend.'

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-semibold text-blue-950">
            <PlayCircle size={16} />
            Workbench data setup
          </div>
          <p className="text-sm text-blue-800">
            {primaryHint} This is an allowlisted backend operation, not arbitrary shell execution.
          </p>
          {needsComponents && needsSurface && (
            <p className="text-xs text-blue-700">After surface is built, run component materialization from this same panel.</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onRunProjection(primaryOperation)}
            disabled={projectionRunning}
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {projectionRunning ? <Loader className="animate-spin" size={16} /> : <PlayCircle size={16} />}
            <span>{primaryLabel}</span>
          </button>
          <button
            type="button"
            onClick={() => onRunProjection('refresh_workbench')}
            disabled={projectionRunning}
            className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm font-medium text-blue-800 hover:bg-blue-100 disabled:opacity-50"
          >
            {projectionRunning ? <Loader className="animate-spin" size={16} /> : <DatabaseZap size={16} />}
            <span>Refresh all read models</span>
          </button>
        </div>
      </div>

      {projectionResult && (
        <div className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-xs text-blue-900">
          <div className="flex items-center gap-2 font-semibold">
            {projectionResult.status === 'failed' ? <AlertCircle size={14} /> : <CheckCircle2 size={14} />}
            {projectionResult.status}: {projectionResult.message}
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            {(projectionResult.steps || []).map((step) => (
              <div key={step.step_id} className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                <div className="font-semibold text-gray-900">{step.step_id} · {step.status}</div>
                <div className="mt-1 text-gray-600">{step.message}</div>
                {step.snapshot_id && <div className="mt-1 truncate text-gray-500">snapshot: {step.snapshot_id}</div>}
                {step.analysis_run_id && <div className="mt-1 truncate text-gray-500">analysis: {step.analysis_run_id}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
