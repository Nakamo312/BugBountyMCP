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
