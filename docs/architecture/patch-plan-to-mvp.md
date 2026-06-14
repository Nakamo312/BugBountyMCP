# Patch plan to MVP

This file is the persistent patch roadmap for the BugBountyMCP target architecture. It exists so the implementation order does not depend on chat context.

MVP means the platform can complete this loop:

```text
ToolActionRequest
  -> policy/scope/approval
  -> transactional outbox
  -> RabbitMQ
  -> worker
  -> raw artifact
  -> parser/processor/ingestor
  -> PostgreSQL canonical facts
  -> OpenSearch projection
  -> Neo4j GraphFacts
  -> LangGraph wait/resume
  -> hypothesis/evidence/report draft
```

The MVP ends after M7. M8 advanced analytics and M9 dashboard are post-MVP.

## Current baseline

Uploaded snapshot: `BugBountyMCP-current(2).zip`.

Existing important components in the snapshot:

- FastAPI API service.
- RabbitMQ event bus.
- PostgreSQL operational source of truth.
- Existing pipeline/node representation.
- `ActionService` / `PolicyService` foundation.
- `pipeline.yaml` with capabilities and workers.
- Raw artifacts metadata and file-based raw output storage.
- OpenSearch projection service: `services/search-indexer`.
- `services/research-engine` exists but is targeted for removal.
- `services/surface-engine` exists from previous patches and should be repurposed as extraction/projection support, not as a central intelligence service.

## Hard ordering rules

1. Do not implement LangGraph before execution core, outbox, raw artifact storage, and projection readiness exist.
2. Do not implement Neo4j GDS before GraphFact contract, projector, graph rebuild and query templates exist.
3. Do not keep `research-engine` as an independent pseudo-intelligence service.
4. Do not let LLMs call RabbitMQ, runners, shell commands, or write DB state directly.
5. Do not put raw artifacts directly into Neo4j, OpenSearch agent-facing indexes, or LangGraph state.
6. Do not treat hypothesis as finding. A finding requires evidence and explicit promotion.

## Phase 0 — architecture baseline

### 0008-docs-target-architecture-and-patch-plan.patch

Add target architecture and patch plan documents.

Expected files:

- `docs/architecture/target-platform.md`
- `docs/architecture/patch-plan-to-mvp.md`

Acceptance:

- Target architecture is present in repository.
- Patch plan is present in repository.
- Document explicitly separates PostgreSQL, RabbitMQ, OpenSearch, Neo4j and LangGraph responsibilities.

## M1 — stabilize execution core

### 0009-execution-contracts-tool-action-request.patch

Introduce formal execution DTO/contracts:

- `ToolActionRequest`
- `ToolActionAccepted`
- `ToolInvocation`
- action/job/run/campaign/correlation identifiers

Acceptance:

- `ToolInvocation` carries action/job/run/program/capability/profile/targets/options/safety/scope/policy/campaign/correlation fields.
- Contract serialization tests exist.
- Options are not lost in DTO conversion.

### 0010-capability-catalog-schema.patch

Introduce or formalize the capability catalog:

- `tool_capabilities`
- `tool_profiles`
- `tool_profile_options`
- `tool_safety_classes`
- `tool_input_schemas`
- `tool_output_schemas`

Acceptance:

- Existing `pipeline.yaml` capabilities can be loaded or mirrored.
- Unknown options are rejected.
- Dangerous option names are blocked.

### 0011-policy-split-capability-scope-risk-approval.patch

Split policy responsibilities:

- `CapabilityPolicy`
- `ScopePolicy`
- `RiskPolicy`
- `ApprovalPolicy`

Acceptance:

- Scope is checked before job creation.
- Active profiles require approval where configured.
- Out-of-scope active targets are blocked.

### 0012-action-request-schema-v2.patch

Extend execution schema for durable action requests:

- `action_request_targets`
- `action_request_options`
- `scope_decisions`
- `approval_requests`
- `approval_decisions`
- `campaigns`
- `campaign_id`, `correlation_id`, `workflow_id`

Acceptance:

- Action creation persists targets and options.
- Policy/scope/approval references are durable.
- Blocked actions do not create jobs.

### 0013-jobs-runs-leases-attempts-schema.patch

Separate logical jobs from concrete run attempts:

- `jobs`
- `tool_runs`
- `node_runs`
- `run_attempts`
- `run_leases`
- `run_errors`
- `run_metrics`

Acceptance:

- One action creates one logical job and one initial run.
- Retry creates a new attempt/run record as appropriate.
- Lease claiming is idempotent.

### 0014-transactional-outbox-schema-and-store.patch

Add transactional outbox:

- `event_outbox`
- `event_inbox`
- normalized `event_store`
- store method that writes action/policy/scope/job/run/outbox in one transaction

Acceptance:

- DB commit can happen without RabbitMQ publish and still leave pending outbox.
- Duplicate outbox event is prevented by idempotency key.

### 0015-outbox-publisher-service.patch

Add outbox publisher:

- `SELECT ... FOR UPDATE SKIP LOCKED`
- publish to RabbitMQ
- attempts, `last_error`, `published_at`

Acceptance:

- Publish failure retries.
- Concurrent publishers do not double-publish the same event.

### 0016-tool-execution-api-v2.patch

Add unified Tool Execution API:

- `POST /tool-actions`
- `GET /tool-actions/{id}`
- `GET /tool-actions/{id}/events`
- `GET /tool-actions/{id}/result`

Legacy `/scan/*` routes become wrappers.

Acceptance:

- API returns `202 Accepted` with action/job/run/campaign/correlation/wait/result identifiers.
- Blocked action returns blocked state and no job.

### 0017-runner-tool-invocation-propagation.patch

Make workers and runners consume `ToolInvocation`.

Acceptance:

- Runner command builders receive typed options.
- Existing runners preserve shell-safe argument-list construction.
- Tests prove options reach at least `httpx`, `katana`, `ffuf`, and `naabu` runners.

### 0018-worker-idempotency-and-work-key.patch

Add event storm controls:

- `work_key`
- dedup/coalescing
- cooldown
- fanout limits
- depth limits
- token bucket / campaign budget fields

Acceptance:

- Same work key does not create duplicate live work.
- Fanout respects budget.

### 0019-campaign-lifecycle.patch

Add bounded expansion lifecycle:

- `created`
- `running`
- `expanding`
- `waiting_for_projections`
- `quiescent`
- `closed`
- `cancelled`
- `failed`

Acceptance:

- Campaign is not quiescent while outbox/jobs/projection lag remain.
- Campaign becomes quiescent only after quiet window.

## M2 — artifact storage cleanup

### 0020-content-addressed-artifact-store.patch

Add content-addressed artifact storage with deduplication.

Acceptance:

- Identical blob is stored once.
- Artifact metadata points to content-addressed blob.
- Raw artifact is recorded before parsing.

### 0021-artifact-compression-and-retention.patch

Add compression and retention policy.

Acceptance:

- Large raw outputs are compressed.
- Retention class is stored and queryable.

### 0022-artifact-preview-and-sanitizer.patch

Add previews and sanitized previews.

Acceptance:

- Authorization/Cookie/Set-Cookie/token-like values are redacted.
- `raw_safe_for_llm=false` by default.
- `sanitized_safe_for_llm=true` only after sanitizer.

### 0023-artifact-lineage.patch

Add artifact lineage:

- parser version
- sanitizer version
- source target
- scope decision
- tool run
- parent artifact

Acceptance:

- Parser output links back to raw artifact.
- Sanitized preview links back to raw artifact and sanitizer version.

## M3 — remove research-engine as service

### 0024-research-engine-inventory-and-freeze.patch

Inventory useful pieces and freeze standalone research-engine expansion.

Acceptance:

- Document lists pieces to move: sanitizer, hypothesis/evidence models, gatekeeper/critic ideas, safe schemas, scoring helpers.
- No new code depends on `services/research-engine`.

### 0025-application-hypotheses-evidence-models.patch

Move research models into application/domain layer:

- hypotheses
- evidence items
- advisory intents
- hypothesis events

Acceptance:

- Hypothesis is not a finding.
- Evidence links to artifact/source.
- State transitions are explicit.

### 0026-critic-verifier-service-skeleton.patch

Add deterministic critic/verifier service.

Acceptance:

- Finding promotion without evidence is rejected.
- Unsafe evidence is rejected.
- Unsupported claims are downgraded/rejected.

### 0027-remove-research-engine-service.patch

Delete standalone `services/research-engine` and compose references.

Acceptance:

- Test suite and compose do not reference `research-engine`.
- Useful code has been moved or explicitly discarded.

## M4 — Neo4j graph projection

### 0028-neo4j-compose-and-settings.patch

Add optional Neo4j profile, settings and driver skeleton.

Acceptance:

- Project works without Neo4j when disabled.
- Settings parse Neo4j URL/user/password.

### 0029-graphfact-contract.patch

Add GraphFact contracts:

- `GraphNodeFact`
- `GraphEdgeFact`
- `GraphFactBatch`

Acceptance:

- Each fact has program/source/tool/confidence lineage.
- Invalid missing source is rejected.
- Deterministic identity key is required.

### 0030-graph-ontology-l0-l1.patch

Add L0/L1 graph backbone cards and constraints:

- Program, Scope, Tool, ToolRun, Artifact, Observation, Evidence
- Domain, Host, IP, ASN, CIDR, Service

Acceptance:

- Each stable label has identity key, sources, relationships, and query use case.
- Property-vs-node rule is documented.

### 0031-neo4j-projector-upsert.patch

Add idempotent Neo4j projector.

Acceptance:

- Same GraphFactBatch applied twice creates no duplicates.
- first_seen/last_seen/confidence/source fields are preserved/updated correctly.

### 0032-graphfact-producers-infra-tools.patch

Add producers for first infrastructure tools:

- subfinder
- dnsx
- naabu
- httpx
- optionally amass

Acceptance:

- Each producer emits expected node/edge facts.
- Facts link to source artifact and tool run.

### 0033-graphfact-producers-web-tools.patch

Add Web/API producers:

- katana
- linkfinder
- nuclei when introduced
- playwright HTTP observations

Acceptance:

- JSFile REFERENCES Endpoint.
- Endpoint HAS_PARAM Parameter.
- Raw header/cookie values are not graph nodes by default.

### 0034-graph-rebuild-command.patch

Add graph rebuild command.

Acceptance:

- Neo4j graph can be rebuilt from PostgreSQL canonical facts and artifact metadata.
- Rebuild is idempotent.

### 0035-graph-query-templates-v1.patch

Add safe graph query templates:

- hidden endpoints from JS
- endpoint neighborhood
- exposed services by technology
- hypothesis evidence paths

Acceptance:

- Every template requires program_id.
- Results are bounded and shaped.

## M5 — OpenSearch expansion

### 0036-opensearch-index-schema-versioning.patch

Add schema versioning for indexes.

Acceptance:

- Documents carry `schema_version`, `sanitizer_version`, `program_id`, `artifact_id`, `tool_run_id` where relevant.

### 0037-opensearch-missing-indexes.patch

Add target indexes:

- `bb-tool-logs`
- `bb-endpoints`
- `bb-technologies`
- `bb-packages`
- `bb-cves`
- `bb-osint-entities`
- `bb-secrets`
- `bb-hypotheses`
- `bb-agent-events`

Acceptance:

- Sensitive fields are not indexed raw.
- Mappings are static and versioned.

### 0038-search-document-producers-v1.patch

Add document producers for artifacts/http/endpoints/technologies/hypotheses.

Acceptance:

- Documents are sanitized and bounded.
- Per-program filtering is supported.

### 0039-opensearch-projection-lag.patch

Add projection watermarks and lag state.

Acceptance:

- `projections_ready` can use OpenSearch lag state.

## M6 — async agent protocol

### 0040-agent-coordination-schema.patch

Add durable agent coordination tables:

- `agent_workflows`
- `agent_workflow_runs`
- `agent_subscriptions`
- `agent_inbox`
- `agent_wait_conditions`
- `agent_result_sets`

Acceptance:

- Subscriptions are scoped by program/campaign/correlation.
- Inbox writes are idempotent.

### 0041-agent-event-router.patch

Route EventStore events into AgentInbox.

Acceptance:

- Relevant event creates inbox message.
- Irrelevant event is ignored.
- Duplicate event is not duplicated.

### 0042-wait-conditions-engine.patch

Add wait condition engine:

- `tool_run_completed`
- `ingestion_completed`
- `projections_ready`
- `new_facts_available`
- `campaign_quiescent`

Acceptance:

- Wait condition resolves only when true.
- Timeout/cancel behavior is explicit.

### 0043-result-sets.patch

Add stable result sets for action/campaign/workflow.

Acceptance:

- Result set links artifacts, facts, search refs and graph refs.
- Result set is fetchable by action/campaign/workflow.

### 0044-agent-protocol-api.patch

Add APIs for subscriptions, inbox ack, wait conditions and result sets.

Acceptance:

- Agent can subscribe, wait, receive inbox message and fetch result set.

## M7 — LangGraph workflows to MVP

### 0045-langgraph-service-skeleton.patch

Add LangGraph workflow runtime skeleton with PostgreSQL checkpointer.

Acceptance:

- State stores IDs and pointers, not raw bodies.
- Workflow can pause and resume.

### 0046-agent-tooling-read-context.patch

Add read-only context tools:

- program context
- OpenSearch search
- graph template query
- result set fetch
- hypotheses fetch
- artifact preview fetch

Acceptance:

- Program boundary is enforced.
- Raw artifacts are denied unless explicit policy allows.

### 0047-cypher-gateway-v1.patch

Add read-only Cypher Gateway.

Acceptance:

- Write clauses are blocked.
- Program boundary is enforced.
- LIMIT and timeout are enforced.
- Query audit is recorded.

### 0048-langgraph-toolaction-tool.patch

Add LangGraph tool for ToolActionRequest creation via API only.

Acceptance:

- Agent cannot call RabbitMQ or runner directly.
- Active action triggers approval where required.

### 0049-langgraph-approval-node.patch

Add human approval node.

Acceptance:

- Workflow pauses on approval.
- Reject stops workflow.
- Approve resumes workflow.

### 0050-hypothesis-builder-workflow.patch

Add first useful hypothesis workflow.

Acceptance:

- Hypothesis is linked to evidence refs.
- No finding is created automatically.

### 0051-critic-verifier-workflow.patch

Add critic/verifier workflow.

Acceptance:

- Scope, missing evidence, unsafe artifacts and unsupported impact are checked.

### 0052-report-builder-draft-workflow.patch

Add report draft workflow.

Acceptance:

- Draft links evidence chain.
- Secrets/cookies/tokens are redacted.
- Missing evidence prevents final report status.

## MVP done

MVP is complete after patch `0052-report-builder-draft-workflow.patch` when the platform can run the full controlled loop from ToolActionRequest to report draft.

## Post-MVP

M8 advanced analytics:

- CVE paths
- endpoint similarity
- hidden paths
- misconfiguration candidates
- business logic workflows
- metamorphic testing
- mutation fuzzing
- Neo4j GDS named projections

M9 unified dashboard:

- execution
- tools
- artifacts
- search
- graph
- agents
- hypotheses
- reports
- metrics
