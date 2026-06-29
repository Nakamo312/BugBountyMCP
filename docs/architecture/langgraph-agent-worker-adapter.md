# LangGraph agent worker adapter

This adapter is the narrow production path between LangGraph-owned agent
workflow execution and the BugBountyMCP domain/control plane.

## Ownership

LangGraph owns:

- agent task workflow execution;
- thread/checkpoint identity;
- role-node orchestration;
- streaming/runtime concerns inside the worker/platform.

The backend owns:

- visible `agent_tasks` and `agent_task_messages` read models;
- `agent_action_proposals` and human review state;
- `ActionService`, scope, policy, approval, and budget;
- artifacts, observations, outcomes, evidence, reports.

The worker must not execute scanners, shell commands, RabbitMQ publishes, or raw
DB writes. It posts typed output through the internal agent protocol.

## Flow

```text
agent task prompt/follow-up
  -> agent_inbox message
  -> external LangGraph agent-task worker claims message
  -> LangGraph thread/run executes role workflow
  -> worker posts typed runtime result to /api/v1/agent/task-runtime-results
  -> backend stores visible task message and proposals
  -> backend acks inbox message only after durable write
```

If the worker proposes an action, it persists only an advisory proposal. A real
run still requires explicit accept and submission through `ActionService`.

## Why this exists

Previous patches introduced local task inbox processing inside the API process.
That remains useful for isolated tests and dev fallback, but production should
not grow a second agent platform inside FastAPI. This adapter lets LangGraph do
what it is good at while keeping bug bounty safety and evidence boundaries in
the domain system.
