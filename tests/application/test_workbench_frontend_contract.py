from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_workbench_page_bundle() -> str:
    return "\n".join([
        _read("BugBountyDashBoard/src/pages/Workbench.jsx"),
        _read("BugBountyDashBoard/src/components/workbench/WorkbenchPanels.jsx"),
    ])


def test_workbench_frontend_uses_flowsint_style_canvas_renderer_for_large_graphs() -> None:
    package = _read("BugBountyDashBoard/package.json")
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")

    assert '"react-force-graph-2d"' in package
    assert "from 'react-force-graph-2d'" in canvas
    assert "ForceGraph2D" in canvas
    assert "nodeCanvasObject" in canvas
    assert "ReactFlow" not in canvas
    assert "@xyflow/react" not in canvas


def test_workbench_frontend_has_dedicated_route_and_navigation_entry() -> None:
    app = _read("BugBountyDashBoard/src/App.jsx")
    layout = _read("BugBountyDashBoard/src/components/Layout.jsx")
    navigation = _read("BugBountyDashBoard/src/navigation/dashboardNavigation.js")

    assert "./pages/Workbench" in app
    assert 'path="/workbench"' in app
    assert "dashboardNavGroups" in layout
    assert "label: 'Workbench'" in navigation
    assert "label: 'Execution'" in navigation
    assert "Agent Workspace" not in navigation


def test_workbench_frontend_calls_typed_workbench_read_apis_only() -> None:
    api = _read("BugBountyDashBoard/src/services/api.js")
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")

    assert "getWorkbenchBootstrap" in api
    assert "getWorkbenchGraph" in api
    assert "getWorkbenchEntity" in api
    assert "getWorkbenchEntityActions" in api
    assert "getWorkbenchAvailableActions" in api
    assert "submitWorkbenchAction" in api
    assert "getWorkbenchEntityMemory" in api
    assert "retrieveWorkbenchEvidence" in api
    assert "/workbench/graph" in api
    assert "/workbench/entities/" in api
    assert "/workbench/actions/available" in api
    assert "/workbench/actions/submit" in api
    assert "getInfrastructureGraph" not in page
    assert "getInfrastructureGraph" not in hook
    assert "runKatana" not in page
    assert "createAction" not in page
    assert "runSubfinder" not in page
    assert "runFFUF" not in page


def test_workbench_lower_panel_renders_materialized_read_side_fragments() -> None:
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")

    assert "Evidence / Memory / Actions" in page
    assert "Context" in page
    assert "Delta summary" in page
    assert "Available actions" in page
    assert "retrieveWorkbenchEvidence" in hook
    assert "setEvidencePack" in hook

def test_workbench_frontend_has_command_palette_filters_saved_views_and_projection_status() -> None:
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")

    assert "CommandBar" in page
    assert "Retrieve context" in page
    assert "filter, type:endpoint, gap, stale, has:actions" in page
    assert "Saved views" in page
    assert "Projection status" in page
    assert "Queue health" in page
    assert "Focus" in page
    assert "setRetrieveQuery" in hook
    assert "query: retrieveQuery.trim() || undefined" in hook
    assert "seed: node.entity_key" in hook


def test_projection_overview_hides_operator_commands_under_advanced_details() -> None:
    overview = _read("BugBountyDashBoard/src/components/dashboard/ProjectionOverview.jsx")
    plan = _read("BugBountyDashBoard/src/components/dashboard/OperatorPlan.jsx")

    assert "Advanced local CLI fallbacks" in overview
    assert "Advanced local projection diagnostics" in overview
    assert "Local fallback commands" in overview
    assert "Advanced local CLI fallback" in plan
    assert "Projection readiness from backend read models" in plan


def test_workbench_canvas_has_read_only_graph_context_menu() -> None:
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")
    page = _read_workbench_page_bundle()

    assert "onNodeRightClick" in canvas
    assert "GraphContextMenu" in canvas
    assert "onBackgroundRightClick" in canvas
    assert "Focus graph from this seed" in canvas
    assert "Copy entity key" in canvas
    assert "Filter left rail by this node type" in canvas
    assert "onFocusNode={focusNode}" in page
    assert "onCopyNodeKey={copyToClipboard}" in page
    assert "onFilterNodeType={(node) => setFilterQuery(`type:${node.node_type}`)}" in page
    assert "createAction" not in canvas
    assert "runKatana" not in canvas


def test_workbench_inspector_groups_sections_and_affordances() -> None:
    page = _read_workbench_page_bundle()

    assert "InspectorTabs" in page
    assert "Profile" in page
    assert "Evidence" in page
    assert "Actions" in page
    assert "Memory" in page
    assert "Available" in page
    assert "Blocked" in page

def test_workbench_frontend_persists_saved_views_and_shows_acceptance_coverage() -> None:
    page = _read_workbench_page_bundle()

    assert "localStorage.setItem(savedViewsStorageKey(programId)" in page
    assert "localStorage.getItem(savedViewsStorageKey(programId))" in page
    assert "Saved views" in page
    assert "Workbench answer coverage" not in page
    assert "document.execCommand('copy')" in page


def test_workbench_page_is_thin_and_panels_live_below_workbench_components() -> None:
    page_path = Path("BugBountyDashBoard/src/pages/Workbench.jsx")
    panels_path = Path("BugBountyDashBoard/src/components/workbench/WorkbenchPanels.jsx")
    page = page_path.read_text(encoding="utf-8")
    panels = panels_path.read_text(encoding="utf-8")

    assert panels_path.exists()
    assert len(page.splitlines()) < 250
    assert "../components/workbench/WorkbenchPanels" in page
    assert "const NodeList" not in page
    assert "const LowerEvidencePanel" not in page
    assert "const Inspector" not in page
    assert "export const NodeList" in panels
    assert "export const LowerEvidencePanel" in panels
    assert "export const Inspector" in panels


def test_workbench_frontend_can_refresh_missing_read_models_without_manual_ids() -> None:
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")
    api = _read("BugBountyDashBoard/src/services/api.js")

    assert "ProjectionControlPanel" in page
    assert "Build surface map" in page
    assert "Materialize components" in page
    assert "Refresh all read models" in page
    assert "Build a Surface Map snapshot" in page
    assert "runWorkbenchProjectionRefresh" in api
    assert "/workbench/projections/run" in api
    assert "runProjectionRefresh" in hook
    assert "operation" in hook
    assert "snapshot_id" not in hook


def test_workbench_surface_canvas_uses_canvas_investigation_map_not_card_grid() -> None:
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")

    assert "Investigation graph" in canvas
    assert "nodeCanvasObject" in canvas
    assert "paintNode" in canvas
    assert "route_family" in canvas
    assert "GraphLegend" in canvas
    assert "workbench-canvas-bounds" in canvas
    assert "ResizeObserver" in canvas
    assert "width={canvasSize.width || 320}" in canvas
    assert "height={canvasSize.height || 320}" in canvas
    assert "WorkbenchNodeCard" not in canvas
    assert "nodePositionMap" not in canvas
    assert "const columns =" not in canvas
    assert "nodePosition(index)" not in canvas


def test_workbench_inspector_prefers_readable_profile_summary_over_empty_json_blob() -> None:
    panels = _read("BugBountyDashBoard/src/components/workbench/WorkbenchPanels.jsx")

    assert "KeyValueGrid" in panels
    assert "Raw profile DTO" in panels
    assert "Host" in panels
    assert "Route" in panels
    assert "Surface nodes" in panels


def test_surface_components_page_can_materialize_latest_without_manual_snapshot_id() -> None:
    page = _read("BugBountyDashBoard/src/pages/SurfaceComponents.jsx")

    assert "Component data setup" in page
    assert "Materialize latest components" in page
    assert "Build surface + components" in page
    assert "Load snapshot by UUID" in page
    assert "runWorkbenchProjectionRefresh" in page
    assert "Open in Workbench" in page
    assert "Neo4j/GDS materialized" in page
    assert "degraded fallback" in page
    assert "Neo4j/GDS unavailable" in page
    assert "The current report is a degraded local grouping." in page
    assert "Retry Neo4j/GDS materialization" in page
    assert "Fallback diagnostics" in page
    assert "Signals" in page
    assert "Graph-projector lanes" in page
    assert "Bridge-heavy" in page
    assert "Outliers" in page
    assert "Low coverage" in page
    assert "Action candidates" in page
    assert "Materialized graph-projector data" in page
    assert "report && isFallbackReport(report)" in page
    assert "report && !isFallbackReport(report)" in page


def test_workbench_canvas_uses_progressive_investigation_controls_for_dense_graphs() -> None:
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")

    assert "DETAIL_GRAPH_LIMIT" in canvas
    assert "OVERVIEW_NODE_LIMIT" in canvas
    assert "selectCanvasGraph" in canvas
    assert "Canvas renderer, hover/select to reveal labels" in canvas
    assert "alwaysLabelTypes" in canvas
    assert "zoomedEnoughForGroupLabels" in canvas
    assert "double click to focus" in canvas
    assert "onNodeDoubleClick" in canvas
    assert "zoomToFit" in canvas
    assert "workbench-canvas-bounds" in canvas
    assert "ResizeObserver" in canvas
    assert "width={canvasSize.width || 320}" in canvas
    assert "height={canvasSize.height || 320}" in canvas
    assert "WorkbenchNodeCard" not in canvas


def test_workbench_deep_links_component_lens_and_keeps_canvas_inside_bounds() -> None:
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")
    panels = _read("BugBountyDashBoard/src/components/workbench/WorkbenchPanels.jsx")
    components = _read("BugBountyDashBoard/src/pages/SurfaceComponents.jsx")

    assert "routeWorkbenchState" in hook
    assert "URLSearchParams(window.location.search)" in hook
    assert "params.get('lens')" in hook
    assert "params.get('seed')" in hook
    assert "`/workbench?lens=components&seed=${encodeURIComponent" in components
    assert "workbench-canvas-bounds" in canvas
    assert "overflow-hidden bg-gray-50" in canvas
    assert "pointer-events-auto" in panels
    assert "relative z-30" in panels
    assert "onMouseDown={(event) => event.stopPropagation()}" in panels
    assert "onClick={(event) => event.stopPropagation()}" in panels
    assert "onMouseDownCapture={(event) => event.stopPropagation()}" not in panels
    assert "touch-action: none" in canvas
    assert "max-width: 100% !important" in canvas
    assert "onMouseDownCapture={(event) => event.stopPropagation()}" not in canvas
    assert "Relationship view unavailable" in canvas
    assert "Select an entity first" in canvas
    assert "Relationship view is not ready" in canvas


def test_surface_components_exposes_graph_projector_source_instead_of_raw_score_dump() -> None:
    components = _read("BugBountyDashBoard/src/pages/SurfaceComponents.jsx")
    backend = _read("src/api/infrastructure/workbench_components.py")

    assert "Projection source:" in components
    assert "Neo4j/GDS materialized" in components
    assert "Neo4j/GDS unavailable" in components
    assert "Action candidates" in components
    assert "Open in Workbench" in components
    assert "surface_map_local_fallback" in backend
    assert "neo4j_gds_materialized" in backend
    assert "gds_execution" in backend


def test_workbench_frontend_exposes_neo4j_projection_lenses_and_canvas_types() -> None:
    app_models = _read("src/api/application/workbench.py")
    backend = _read("src/api/infrastructure/workbench_neo4j.py")
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")

    assert "NEO4J_EXPOSURE" in app_models
    assert "NEO4J_ENDPOINT" in app_models
    assert "NEO4J_EVIDENCE" in app_models
    assert "NEO4J_SURFACE_MATH" in app_models
    assert "NEO4J_ACTION_OUTCOME" in app_models
    assert "NEO4J_JS" in app_models
    assert "NEO4J_TECH" in app_models
    assert "NEO4J_HYPOTHESIS" in app_models
    assert "default_query_template_registry" in backend
    assert "asset_exposure" in backend
    assert "endpoint_neighborhood" in backend
    assert "evidence_path" in backend
    assert "surface_graph_math" in backend
    assert "action_outcome_experience_neighborhood" in backend
    assert "hidden_endpoints_from_js" in backend
    assert "exposed_services_by_technology" in backend
    assert "hypothesis_evidence_paths" in backend
    assert "raw_cypher" in backend and "forbidden" in backend
    assert "gds_execution" in backend and "forbidden_in_workbench_request_path" in backend
    assert "render_as_graph_node" in backend
    assert "neo4j-message" not in backend
    assert "neo4j_surface_node" in canvas
    assert "neo4j_action_outcome" in canvas
    assert "relationship data" in canvas


def test_dashboard_navigation_groups_workflows_instead_of_backend_pages() -> None:
    navigation = _read("BugBountyDashBoard/src/navigation/dashboardNavigation.js")
    layout = _read("BugBountyDashBoard/src/components/Layout.jsx")
    app = _read("BugBountyDashBoard/src/App.jsx")
    copy_guidelines = _read("docs/frontend/dashboard-copy-guidelines.md")

    assert "Program Overview" in navigation
    assert "Workbench" in navigation
    assert "Execution" in navigation
    assert "Action Catalog" in navigation
    assert "Component Analysis" not in navigation
    assert "Evidence" not in navigation
    assert "Infrastructure Map" not in navigation
    assert "graph/infrastructure" not in app
    assert "dashboardNavGroups.map" in layout
    assert 'path="/execution"' in app
    assert 'path="/graph/components"' in app and 'lens="components"' in app
    assert 'path="/graph/pipeline"' in app and 'diagnostics="projection"' in app
    assert 'path="/hosts"' in app and 'lens="surface"' in app
    assert 'path="/analysis"' in app and 'lens="coverage"' in app
    assert "Command Center" not in navigation
    assert "Agent Workspace" not in navigation
    assert "UI uses English interface text only" in copy_guidelines
    assert "Command Center" in copy_guidelines


def test_execution_copy_distinguishes_agent_tasks_from_executable_actions() -> None:
    workspace = _read("BugBountyDashBoard/src/components/agents/AgentWorkspacePanels.jsx")
    runtime = _read("BugBountyDashBoard/src/components/agents/AgentRuntimeControls.jsx")

    assert "Execution" in workspace
    assert "Agent tasks" in workspace
    assert "Action queue" in workspace
    assert "operator-controlled" not in workspace
    assert "label: 'Manual'" in runtime
    assert "No model call" in runtime


def test_execution_workspace_surfaces_action_queue_status_toasts() -> None:
    hook = _read("BugBountyDashBoard/src/hooks/useAgentWorkspace.js")
    panels = _read("BugBountyDashBoard/src/components/agents/AgentWorkspacePanels.jsx")

    assert "queueNotifications" in hook
    assert "trackQueueStatusChanges" in hook
    assert "queueNotificationForTransition" in hook
    assert "loadWorkspace({ silent: true })" in hook
    assert "queueNotificationForRemovedAction" in hook
    assert "QueueNotificationToasts" in panels
    assert "Action started" in hook
    assert "Action output is being ingested" in hook
    assert "Action left active queue" in hook
    assert "Dismiss notification" in panels
