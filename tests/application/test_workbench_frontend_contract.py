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

    assert "./pages/Workbench" in app
    assert 'path="/workbench"' in app
    assert "label: 'Workbench'" in layout
    assert "label: 'Agent Workspace'" in layout


def test_workbench_frontend_calls_typed_workbench_read_apis_only() -> None:
    api = _read("BugBountyDashBoard/src/services/api.js")
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")

    assert "getWorkbenchBootstrap" in api
    assert "getWorkbenchGraph" in api
    assert "getWorkbenchEntity" in api
    assert "getWorkbenchEntityActions" in api
    assert "getWorkbenchEntityMemory" in api
    assert "retrieveWorkbenchEvidence" in api
    assert "/workbench/graph" in api
    assert "/workbench/entities/" in api
    assert "getInfrastructureGraph" not in page
    assert "getInfrastructureGraph" not in hook
    assert "runKatana" not in page
    assert "createAction" not in page


def test_workbench_lower_panel_renders_materialized_read_side_fragments() -> None:
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")

    assert "Evidence timeline / memory tree / action run log / delta panel" in page
    assert "Recent memory fragments" in page
    assert "Delta summary" in page
    assert "Backend action affordances" in page
    assert "retrieveWorkbenchEvidence" in hook
    assert "setEvidencePack" in hook

def test_workbench_frontend_has_command_palette_filters_saved_views_and_projection_status() -> None:
    page = _read_workbench_page_bundle()
    hook = _read("BugBountyDashBoard/src/hooks/useWorkbench.js")

    assert "CommandBar" in page
    assert "retrieve query for selected entity, not a prompt blob" in page
    assert "filter, type:endpoint, gap, stale, has:actions" in page
    assert "Saved views" in page
    assert "Projection status" in page
    assert "Queue health" in page
    assert "Focus" in page
    assert "setRetrieveQuery" in hook
    assert "query: retrieveQuery.trim() || undefined" in hook
    assert "seed: node.entity_key" in hook


def test_workbench_canvas_has_read_only_graph_context_menu() -> None:
    canvas = _read("BugBountyDashBoard/src/components/workbench/WorkbenchCanvas.jsx")
    page = _read_workbench_page_bundle()

    assert "onNodeRightClick" in canvas
    assert "GraphContextMenu" in canvas
    assert "onBackgroundRightClick" in canvas
    assert "Focus graph from this seed" in canvas
    assert "Copy entity key" in canvas
    assert "Filter left rail by this node type" in canvas
    assert "does not submit actions, proposals, or graph mutations" in canvas
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
    assert "Enabled by backend" in page
    assert "Blocked or read-only" in page
    assert "does not submit actions" in page

def test_workbench_frontend_persists_saved_views_and_shows_acceptance_coverage() -> None:
    page = _read_workbench_page_bundle()

    assert "localStorage.setItem(savedViewsStorageKey(programId)" in page
    assert "localStorage.getItem(savedViewsStorageKey(programId))" in page
    assert "Saved views persist locally per program" in page
    assert "Workbench answer coverage" in page
    assert "What is this entity?" in page
    assert "Where did it come from?" in page
    assert "What changed recently?" in page
    assert "What evidence supports it?" in page
    assert "Which actions are available now?" in page
    assert "not a vulnerability verdict or confidence score" in page
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
    assert "No snapshot id or docker command required" in page
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
    assert "backend resolves snapshot ids" in page
    assert "Advanced: load a specific snapshot by UUID" in page
    assert "runWorkbenchProjectionRefresh" in page
    assert "Open in Workbench" in page
    assert "Neo4j/GDS materialized" in page
    assert "degraded fallback" in page
    assert "Why inspect this component" in page
    assert "Graph-projector lanes" in page
    assert "Bridge-heavy" in page
    assert "Outliers" in page
    assert "Low coverage" in page
    assert "Action candidates" in page
    assert "Materialized graph-projector data" in page


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
    assert "onMouseDownCapture={(event) => event.stopPropagation()}" in panels
    assert "contain: layout paint size" in canvas
    assert "max-width: 100% !important" in canvas


def test_surface_components_exposes_graph_projector_source_instead_of_raw_score_dump() -> None:
    components = _read("BugBountyDashBoard/src/pages/SurfaceComponents.jsx")
    backend = _read("src/api/infrastructure/workbench_components.py")

    assert "Projection source:" in components
    assert "Neo4j/GDS materialized" in components
    assert "Neo4j/GDS component analytics were unavailable" in components
    assert "Backend action candidate signals" in components
    assert "Open in Workbench" in components
    assert "surface_map_local_fallback" in backend
    assert "neo4j_gds_materialized" in backend
    assert "gds_execution" in backend
