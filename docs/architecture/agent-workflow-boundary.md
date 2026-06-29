# Agent workflow boundary

This project must not grow a second agent platform beside LangGraph.

LangGraph owns agent workflow execution: thread identity, checkpoints,
interrupt/resume, streaming, and role-node orchestration. The API/domain layer
owns bug-bounty state: campaign tasks, visible messages, proposals, approvals,
action requests, artifacts, outcomes, evidence, and reports.

The intended flow is:

```text
UI prompt
  -> agent_tasks / visible task message
  -> LangGraph thread/run (internal worker or LangGraph platform)
  -> typed agent reply or proposal
  -> agent_task_messages / agent_action_proposals
  -> explicit human or scheduler decision
  -> ActionService
  -> policy / scope / approval / budget
  -> job / run / artifact / outcome memory
```

Do not expose LangGraph run controls, graph/GDS probes, model-runtime toggles, or
agent execution as public product APIs. Product APIs may create prompts, append
follow-ups, read persisted task state, accept/reject/suppress proposals, and
submit actions through the control plane.

Keep these as domain/read-model concepts:

- `agent_tasks`: product-facing task cards and prompt metadata.
- `agent_task_messages`: persisted visible transcript and decision events.
- `agent_action_proposals`: typed bridge from agent output to control-plane
  action intent.
- workspace/task/activity read models: UI snapshots over persisted domain state.

Avoid these anti-patterns:

- starting an agent-task runtime loop inside the FastAPI process;
- treating `agent_inbox` as a replacement for LangGraph queues/runs;
- writing custom checkpoint/thread/stream semantics that duplicate LangGraph;
- letting a LangGraph node launch scanners, publish RabbitMQ events, or write raw
  artifact state directly;
- adding public endpoints that synchronously run internal reasoning, GDS probes,
  or agent workflows.

A local bridge may exist for tests and development, but production wiring should
prefer an internal LangGraph worker/platform adapter that consumes prompts,
executes the LangGraph thread, and writes typed domain output back through the
existing application services.
