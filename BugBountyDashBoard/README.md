# Bug Bounty Dashboard

React dashboard for BugBountyMCP. The current UI direction is action-oriented:
actions replace scan-specific pages as the primary way to launch controlled
tool execution.

## Main Areas

- Program selection and program management.
- Action launch forms backed by API capability metadata.
- Dashboard views for discovered hosts and endpoints.
- API client helpers in `src/services/api.js`.

## Local Setup

```bash
npm install
npm run dev
```

The development server is normally available at `http://localhost:3000`.

## API Proxy

The Vite proxy targets the backend API. If the backend runs on a different
port, update `vite.config.js`:

```js
proxy: {
  "/api": {
    target: "http://localhost:YOUR_PORT",
    changeOrigin: true,
  },
}
```

## Structure

```text
src/
  components/
    actions/
      configs/
      forms/
      hooks/
      ui/
  context/
  pages/
    Actions/
    Dashboard.jsx
  services/
    api.js
  App.jsx
  main.jsx
```

## Notes

- Keep action components aligned with backend action/capability contracts.
- Do not reintroduce scan-only pages as the main workflow.
- Prefer typed API helpers over ad hoc request logic in components.



## Projection Pipeline and Operator Plan

The dashboard home page reads `/api/v1/program-projection-overview` and `/api/v1/program-projection-overview/plan` for the selected program. It renders freshness flags, durable queue backlog, pending experience proposal counts, suggested commands, an ordered read-only operator plan, and CLI commands for inspecting the local `projection run-step` audit trail. The browser does not read `.bb/audit/projection-run-step.jsonl`; audit inspection remains a local `bb projection audit` / `bb projection audit-summary` workflow. This UI path is diagnostic only: it never runs Neo4j/GDS, retries queues, rebuilds projections, materializes analysis, reindexes OpenSearch, creates proposals, submits actions, or executes tools.

## Surface Components

The `/surface-components` page reads persisted Surface Component analysis from
`/api/v1/surface-component-analysis/latest`. It is a read-only UI over the
PostgreSQL materialized read model and does not run Neo4j/GDS, materialize new
reports, create proposals, or submit actions.

## Program Projection Overview

The Dashboard page reads `GET /api/v1/program-projection-overview` for the
selected program and renders a read-only pipeline card. It shows Surface Map
analysis freshness, OpenSearch projection freshness, queue backlog/error counts,
pending experience proposals, and suggested operator commands. The page does not
run Neo4j/GDS, retry queues, rebuild graphs, materialize analysis, reindex
OpenSearch, create proposals, or submit actions.
