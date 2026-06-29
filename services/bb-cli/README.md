# bb-cli

`bb-cli` is the terminal interface for the research control plane. It exists
before a polished web workflow so operator UX can be validated without adding
frontend-only behavior.

The CLI is intentionally thin:

- talks only to the FastAPI control-plane API;
- does not connect to Postgres, Neo4j, LangGraph, RabbitMQ, or runners;
- does not execute tools directly;
- accepts proposals only by submitting them through the existing ActionService
  boundary, where scope, policy, approval, and budget still apply.

## Environment

```bash
export BB_API_URL=http://localhost:8000
export BB_PROGRAM_ID=<program-uuid>
export BB_CAMPAIGN_ID=<campaign-uuid>   # optional
export BB_CREATED_BY=cli                # optional
export BB_API_TOKEN=<token>             # optional, if API auth is enabled
```

## Core workflow

```bash
python -m bb_cli workspace
python -m bb_cli task create "разбери новые JS и предложи следующий шаг" --agent artifacts --mode none
python -m bb_cli task list
python -m bb_cli task show <task-id>
python -m bb_cli task reply <task-id> "это шум, больше не предлагай похожее"
python -m bb_cli task run-agent <task-id>
python -m bb_cli proposal list
python -m bb_cli proposal accept <proposal-id> --target https://example.com
python -m bb_cli proposal reject <proposal-id> --reason "слишком абстрактно"
python -m bb_cli proposal suppress <proposal-id> --reason "повтор"
python -m bb_cli proposal accept <experience-proposal-id> --kind experience --target https://example.com
python -m bb_cli proposal reject <experience-proposal-id> --kind experience --reason "не та ветка"
python -m bb_cli proposal suppress <experience-proposal-id> --kind experience --reason "повторный шум"
python -m bb_cli --program-id <uuid> projection overview
python -m bb_cli --program-id <uuid> projection plan
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events --execute --yes
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events --audit-log ./ops-audit.jsonl
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events --no-audit
python -m bb_cli --program-id <uuid> projection audit
python -m bb_cli --program-id <uuid> projection audit --step-id process-search-projection-events
python -m bb_cli --program-id <uuid> projection audit-summary
python -m bb_cli --program-id <uuid> projection audit-summary --step-id process-search-projection-events
python -m bb_cli activity
```

`task run-agent` invokes one external `agent_worker run-once` sweep and then,
when a task id is provided, reloads that task detail. It does not become an
agent runtime. The spawned worker still talks to the backend internal agent
boundary and tools still require `ActionService` through proposal acceptance.

`proposal list` renders both user-facing agent action proposals and internal action-experience proposals from the workspace read model. Agent proposals remain the default for backward compatibility. Use `--kind experience` when accepting, rejecting, or suppressing graph/GDS action-experience proposals. Accepting either proposal kind only submits through `ActionService`; it never runs tools directly.

`projection overview` renders the read-only `/api/v1/program-projection-overview` state for the current program: latest Surface Map snapshot, latest persisted component analysis, graph/search queue backlogs, pending experience proposals, freshness flags, and suggested operator commands. `projection plan` renders `/api/v1/program-projection-overview/plan`, an ordered list of operator commands derived from that same overview. Both commands are diagnostic only and never run GDS, rebuild, retry, materialization, OpenSearch reindex, proposal creation, action submission, or tools.

`projection run-step <step_id>` is a controlled CLI wrapper for one step from the backend operator plan. It previews selected commands by default, validates them against a fixed allow-list using the canonical module command form (`python -m graph_projector`, `python -m search_indexer`, and only read-only `python -m bb_cli ... proposal list` / `python -m bb_cli ... projection overview` commands), and runs them only when both `--execute` and `--yes` are present. Commands are executed without a shell. Preview and execute invocations write a local JSONL audit event by default to `.bb/audit/projection-run-step.jsonl`; `--audit-log` overrides the path and `--no-audit` disables local audit logging. `projection audit` reads that local JSONL file, filters by program/step, and renders recent preview/execute history without contacting the backend or running commands. `projection audit-summary` reads the same local log and aggregates preview/execute/status counts by operator step for a faster ops view. This command still does not submit actions or bypass policy; it only invokes existing operator CLIs selected from the plan.

Add `--json` to any command to inspect the raw API response.

## Worker environment

```bash
export BB_AGENT_INTERNAL_TOKEN=<internal-token> # mapped to AGENT_PROTOCOL_INTERNAL_TOKEN for task run-agent
export PYTHONPATH=src:services/agent-worker:services/bb-cli
```
