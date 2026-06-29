# Передача контекста для нового чата

## Что это за проект

Это не очередной scanner и не rule engine вида «если видишь X, ищи Y». Цель —
исследовательская система, где полезное поведение возникает из контура:

```text
состояние -> действие -> изменившееся представление -> память -> feedback -> новый выбор
```

Код не должен заранее знать, где баг. Код должен хранить опыт действий,
сжимать поверхность в графовые представления, считать изменения структуры и
помогать системе лучше выбирать следующий шаг.

Текущая формула после patch 0041:

```text
PostgreSQL = canonical memory / source of truth
Neo4j/GDS = structural signal engine over typed projections
OpenSearch/RAG = fast retrieval over accumulated evidence
RLM = deep recursive analysis over selected working context
LangGraph agents = policies/roles over memory/projections
CLI tools = effectors after hypothesis and ActionService approval
Deterministic domain code = normalization, diff, scope, policy, budgets, evidence, projections
```

RAG и RLM не являются одним слоем. RAG быстро достаёт evidence refs и bounded
summaries. RLM глубоко анализирует выбранный working context и возвращает
analysis summary, hypothesis proposals и missing observations. Ни один из них не
запускает tools.

Neo4j/GDS считает structural signals: components, bridges, centrality,
similarity, coverage, drift, neighborhoods и missing-relation candidates. Он не
выдаёт bug verdict и не запускает actions.

CLI tools остаются effectors. Любой запуск идёт только через:

```text
ActionService -> policy -> scope -> approval -> budget -> CommandInvocation -> runner
```

Главный вопрос перед каждым патчем:

```text
что это даст системе для выбора следующего действия, экономии бюджета,
памяти опыта или защиты от повторения мусора?
```

Если ответ неясен, патч не нужен.

## Обязательный документ перед продолжением

Перед новым изменением прочитать:

```text
docs/architecture/current-state-sync.md
```

Это текущий sync-документ. Он фиксирует, что уже было в исходной архитектуре, что
уже реализовано после последних патчей, что осталось планом и какие слои нельзя
строить второй раз.

## Patch 0041 status

Patch `0041_research_operating_model_and_graph_math_role` фиксирует курс в:

```text
docs/architecture/research-operating-model.md
docs/architecture/graph-math-role.md
AGENTS.md
README.md
docs/README.md
HANDOFF_FOR_NEW_CHAT.md
```

Он не добавляет runtime feature. Его задача — закрепить experience-first
operating model и graph math role перед graph backlog, typed projections,
credential runtime или orchestration-store cleanup.

Жёсткое правило после 0041: vulnerability labels вроде `IDOR`, `CSRF`,
`JWT-tamper`, `SSRF`, `admin`, `auth-boundary` могут быть post-hoc annotations,
search facets или report labels. Они не являются action engine.

## Patch 0043 status

Patch `0043_extract_run_claim_store` performs the first production split of
`OrchestrationStore`. New file:

```text
src/api/infrastructure/orchestration/run_claim_store.py
```

`RunClaimStore` now owns `claim_node_run`, claim-key idempotency, retryable
failed work reuse, cooldown blocking, campaign budget lock/refill/block/consume,
run insertion, insert-race fallback and coalesced trigger append.

`OrchestrationStore.claim_node_run(...)` remains as a compatibility facade and
delegates to `self.run_claims.claim_node_run(...)`. Application services should
not grow new dependencies on the old private claim helpers. New claim logic goes
into `RunClaimStore`.

Patch `0044_refactor_run_claim_store_flow` then cleans the extracted flow without
changing the external application API. `RunClaimStore.claim_node_run(...)` is now
a compatibility wrapper that packs a `RunClaimRequest`; the internal workflow is
phased through retry reuse, cooldown, budget reservation, run insert and
insert-race recovery. Claim internals now use `ExistingWorkClaim`,
`CampaignBudgetSnapshot`, and `CampaignBudgetReservation` instead of spreading
raw row mappings through the whole flow.

Patch `0045_extract_dispatch_and_scheduled_work_stores` extracts dispatch and scheduled work boundaries. `DispatchStore` now owns outbox enqueue, notify statement, dispatch claim leasing, sent transition, and failed/dead transition. `ScheduledWorkStore` now owns scheduled work queue lifecycle only: scheduled active counts, ready-run leasing, stale lease recovery, stale active-run failure, retry requeue, and exhausted retry transition to dead. It must not grow reconciliation, campaign budget, run accounting, or event emission scenarios.

Patch `0046_extract_action_approval_campaign_stores` extracts action command creation, approval state, campaign lifecycle/accounting, and durable event persistence. `OrchestrationStore` remains a compatibility facade. Direct behavior tests now cover `DispatchStore` and `ScheduledWorkStore`, not just facade delegation and source-grep guards.

Patch `0047_extract_action_read_and_run_state_stores` extracts action read models and runner state transitions. `OrchestrationStore` is now mostly a compatibility facade.

Patch `0048_refactor_graph_projector_cli_entrypoint` makes `graph_projector.__main__` a thin entrypoint and moves parser, handlers, services, command groups, and output rendering into named CLI modules. Patch `0049_fixup_graph_projector_cli_composition` then adds the shared GraphFact enqueuer factory and shared enqueue once/loop runners.

Deferred scheduled-work smell: retry requeue still preserves the old select-ids-then-update model and per-row update loop. Future behavior-changing cleanup should address concurrency with `FOR UPDATE SKIP LOCKED` or a guarded `UPDATE ... RETURNING` boundary before changing semantics.

## Patch 0042 status

Patch `0042_orchestration_store_split_plan_and_characterization_tests` фиксирует
следующий cleanup-блок вокруг `src/api/infrastructure/orchestration/store.py`.

Новый документ:

```text
docs/architecture/orchestration-store-split-plan.md
```

Смысл: `OrchestrationStore` сейчас остаётся facade, но больше не считается
здоровой границей. Его нужно резать по transaction/write scenarios, а не по
таблицам. Целевые stores:

```text
ActionCommandStore
ApprovalStore
RunClaimStore
CampaignStateStore
ScheduledWorkStore
DispatchStore
EventStore
ActionReadStore
```

Первый кодовый extraction после 0042 уже сделан в patch 0043: `RunClaimStore`
вынесен в отдельный scenario-owned store.

Правило: не добавлять слой поверх `OrchestrationStore`. Сохранять
`OrchestrationStore` как временный compatibility facade и выносить реальные
transaction surfaces внутрь узких stores.

До движения кода должны оставаться characterization tests на claim/retry/budget/
coalescing/dispatch semantics.

## Что уже реализовано

### Action outcome / experience

`ActionOutcomeMemory` уже есть и подключён к terminal run path. Завершённые
действия пишут `action_outcomes` с lineage, capability/profile, telemetry,
feedback, score breakdown и utility.

Raw novelty counters больше не должны считаться качественной новизной. Поля
вида `new_hosts_count`, `new_services_count`, `new_endpoints_count`,
`new_graph_facts_count`, `new_search_documents_count` могут жить как telemetry,
но не как основной score.

`information_gain_score` сейчас фактически используется как historical utility
для GDS ranking. Название устарело: после `decision_shift` это уже не только
information gain, а experience utility.

### Credential refs / secret storage

Authenticated scans are supported through `credential_ref` + `auth_injection`,
not through raw tokens in action options. Secret storage foundation now exists:
`credential_refs`, `credential_secret_versions`, and `credential_leases`.

Use this model for future IDOR/authz/session work:

```text
identity metadata -> credential_ref
secret material -> encrypted/local secret version
approved action -> short-lived lease
runner injector -> materializes secret only at execution time
```

Do not put raw cookies, Authorization headers, API keys, session tokens, or
password-like values into proposals, action options, graph/search projections,
LangGraph state, logs, process events, parser payloads, or raw artifact metadata.

### Proposal loop

Уже есть internal advisory proposal stream:

```text
action_experience_proposal_runs
action_experience_proposals
```

Proposals ничего не выполняют напрямую. Исполнение всё равно должно идти через:

```text
proposal -> ActionService -> policy -> scope -> approval -> budget -> run
```

Feedback по proposal хранится на proposal, а не на source outcome. `accepted`,
`rejected`, `suppressed` влияют на future proposal priors, но не портят память
действия, которое породило исходную поверхность.

### Decision shift

После генерации proposals сохраняется decision distribution и decision shift:

```text
entropy
top-k overlap
total variation distance
rank movement
focus gain
decision_shift_score
```

Это текущий механизм качественной дельты на уровне выбора: действие ценно, если
после него изменилось поле следующих действий.

### Surface Map runtime

Исходная схема Surface Map уже была заложена в миграциях и ADR. Сейчас runtime
тоже пишет:

```text
surface_snapshots
surface_nodes
surface_edges
surface_deltas
```

`surface-engine` строит shape-based nodes/edges/deltas без ручных labels типа
`admin`, `api`, `auth`, `swagger`, `docs`.

### Neo4j/GDS math

Есть два GDS-контура.

Первый, исходный:

```text
ActionOutcome <-> OutcomeFeature
  -> gds.nodeSimilarity.stream
  -> learned capability/profile ranking
```

Второй, добавленный для Surface Map:

```text
SurfaceNode --SURFACE_EDGE-- SurfaceNode
  -> WCC / degree / betweenness / nodeSimilarity
  -> component pressure, drift, bridges, outliers, coverage, action candidates
```

Файл:

```text
services/graph-projector/graph_projector/surface_gds.py
```

Методы:

```text
connected_components()
component_profiles()
component_drift()
component_bridges()
component_outliers()
component_coverage()
component_action_candidates()
```

Это не semantic-rule слой. Он считает графовую структуру: компоненты,
центральность, похожесть, дрейф, покрытие и похожий исторический опыт.

### Component proposals

`component_action_candidates()` материализуются в обычный proposal stream. Их
source:

```text
neo4j-gds-surface-component-nodeSimilarity
```

Они остаются advisory и не обходят control plane.

### Mutable graph projection lifecycle

`ActionOutcome` теперь mutable graph source. После пересчёта utility и snapshot
links writer заменяет stale derived edges:

```text
HAS_OUTCOME_FEATURE
BEFORE_SURFACE_SNAPSHOT
AFTER_SURFACE_SNAPSHOT
```

Это нужно, чтобы Neo4j/GDS не видел старые feature buckets и старые snapshot
links одновременно с новыми.

### Graph projector ops

Есть selective rebuild:

```bash
python -m graph_projector rebuild --source action_outcomes
python -m graph_projector rebuild --source surface_map
```

Есть read/repair commands:

```bash
python -m graph_projector status
python -m graph_projector retry
python -m graph_projector health
python -m graph_projector diagnostics
```

Есть materialized read model для surface component analytics:

```bash
python -m graph_projector surface-components-materialize
python -m graph_projector surface-components-materialized
```

Таблицы:

```text
surface_component_analysis_runs
surface_component_analysis_items
```

Первый command запускает существующий GDS report и сохраняет per-component
metrics. Второй читает последний сохранённый результат без повторного GDS run.

Есть read-only API endpoints для UI/скриптов:

```http
GET /api/v1/surface-component-analysis?program_id=<uuid>&snapshot_id=<uuid>
GET /api/v1/surface-component-analysis/latest?program_id=<uuid>
```

Оба endpoint читают только persisted PostgreSQL read model, не запускают
Neo4j/GDS, не создают proposals и не отправляют actions. `latest` нужен UI,
чтобы показать последний materialized report без ручного ввода snapshot id.

Frontend имеет страницу:

```text
/surface-components
```

Есть OpenSearch targets для surface read models:

```bash
python -m search_indexer reindex --target surface-components --program-id <uuid>
python -m search_indexer reindex --target surface-components --program-id <uuid> --analysis-run-id <analysis_run_uuid>
python -m search_indexer reindex --target surface-components --program-id <uuid> --snapshot-id <snapshot_uuid>
python -m search_indexer reindex --target surface-deltas --program-id <uuid>
python -m search_indexer reindex --target surface-deltas --program-id <uuid> --snapshot-id <snapshot_uuid>
```

Они читают только PostgreSQL (`surface_component_analysis_*`, `surface_deltas`)
и не запускают Neo4j/GDS. `--analysis-run-id` индексирует один materialized
component-analysis run, а `--snapshot-id` ограничивает components по
`snapshot_id` и deltas по `to_snapshot_id`.

После successful `surface_component_analysis_event` materialization graph-projector теперь пишет downstream OpenSearch events в отдельную durable queue:

```text
search_projection_events
```

Search-indexer обрабатывает её командами:

```bash
python -m search_indexer process-events
python -m search_indexer process-events --target surface-components
python -m search_indexer process-events --target surface-deltas
python -m search_indexer process-events-loop
```

Очередь имеет собственную ops-видимость и repair path:

```bash
python -m search_indexer status
python -m search_indexer retry
python -m search_indexer health --json
python -m search_indexer diagnostics --json
```

События запускают только incremental reindex с уже сохранёнными фильтрами `analysis_run_id` / `snapshot_id`. Они не запускают Neo4j/GDS и не материализуют новый analysis report.

Она читает materialized Surface Component analysis через API и показывает
pressure/drift/bridge/outlier/coverage/exploration scores и advisory action
candidates. Она не запускает GDS и не материализует новые отчёты.

Они работают с durable PostgreSQL queues:

```text
graph_projection_events
graph_fact_batches
surface_component_analysis_events
search_projection_events
```


## Program Projection Overview

Есть единый read-only endpoint для среза projection/materialization/search pipeline:

```http
GET /api/v1/program-projection-overview?program_id=<uuid>
```

Он читает только PostgreSQL durable state: latest surface snapshot, latest persisted
Surface Component analysis, graph projection queues, surface analysis queue, search
projection queue и action-experience proposal counts.

Он возвращает:

```text
surface_analysis_fresh
search_index_fresh
ui_data_fresh
suggested_commands
```

Boundary: не запускает Neo4j/GDS, retry, rebuild, materialization, OpenSearch
reindex, proposals, actions или tools.

Dashboard now consumes this endpoint as a read-only Projection Pipeline card. It shows freshness flags, queue backlogs, pending experience proposal counts, suggested operator commands, the ordered operator plan from `/api/v1/program-projection-overview/plan`, and local CLI audit inspection commands for `projection run-step` history without starting any backend work. The browser does not read the operator's local JSONL audit file; audit history remains a `bb projection audit` / `bb projection audit-summary` CLI workflow.

## Что не делать

Не строить заново:

```text
ActionOutcomeMemory
action experience proposal tables
GDS nodeSimilarity по outcomes
surface snapshot/node/edge/delta writer
Surface Map Neo4j projection
surface_gds.py readers
surface component analysis materialization
component proposal materialization
proposal review guard / priors
decision shift
mutable ActionOutcome projection refresh
status/retry/health/diagnostics
surface component analysis event queue / worker
search projection event queue / worker
search-indexer status/retry/health/diagnostics
program projection overview endpoint
program projection operator plan endpoint
dashboard program projection overview card
dashboard operator plan display
```

Не добавлять закрытую semantic ontology как ядро scoring:

```text
AUTH_BOUNDARY
API_SURFACE
ADMIN_PANEL
SSRF_HINT
IDOR_HINT
```

Такие labels могут появиться позже только как объяснение/подпись кластера, но не
как основной utility score.

Не делать LLM центром системы. LLM может подписывать, объяснять, сжимать и
помогать человеку, но не должен напрямую вызывать runners, писать в БД, обходить
policy или превращать сырые данные в findings.


## Credential / Secret Boundary

Следующий крупный блок после cleanup — credential lease layer для
авторизованных сканов и запросов. Принятая граница такая:

```text
agent/proposal/action options
  -> opaque credential_ref
  -> ActionService policy/scope/approval/budget
  -> short-lived lease
  -> runner-local injection
  -> artifact/log/process-event sanitization
```

Агентам, LLM, proposal payloads, dashboard, OpenSearch, Neo4j и LangGraph state
нельзя отдавать raw токены, cookies, Authorization headers, API keys или session
material. Они должны видеть только opaque `credential_ref`.

`CommandInvocation` уже содержит поле `credential_refs`, но оно пока не резолвит
секреты. Это подготовительная инфраструктурная граница. Реальное хранилище, TTL,
lease issuance, injection и audit нужно делать отдельным epic.

Не класть секреты в `argv`, `stdin`, runner logs, `ProcessEvent`, parser output,
raw artifact metadata, proposal explanations или read models. Authenticated
action всё равно проходит обычный control plane: capability/profile validation,
scope, policy, approval и budgets.

## Что осталось сделать

Следующий крупный шаг после 0041 — не runtime feature, а cleanup/contract work.

Рекомендуемая очередь:

1. Done: OrchestrationStore split plan + characterization tests.
2. Done: `RunClaimStore` extracted behind the existing facade, without changing external application services.
3. Done: `RunClaimStore` flow refactored into named phases and typed internal DTOs.
4. Done: `DispatchStore` and `ScheduledWorkStore` extracted behind compatibility facade methods.
5. Done: `ActionCommandStore`, `ApprovalStore`, `CampaignStateStore`, and `EventStore` extracted behind compatibility facade methods.
6. Done: `ActionReadStore` and `RunStateStore` extracted; `OrchestrationStore` is now a compatibility facade.
7. Done: `graph_projector.__main__` refactored into a thin CLI entrypoint with parser, handlers, command groups, service builders, output rendering, shared enqueuer factory, and shared enqueue runners.
8. Done: graph backlog extraction documented in `docs/architecture/graph-algorithm-backlog.md`; parser command choices now have a contract test against `GraphProjectorCli.COMMAND_HANDLERS`.
9. Next: typed projection contracts: `G_asset`, `G_http`, `G_identity`, `G_finding`, `G_temporal`, `G_bipartite_endpoint_param`, `G_bipartite_host_tech`, `G_bipartite_endpoint_object`.
10. Credential runtime patches only after the course and store boundaries stop drifting.

Do not start with temp-file manager, credential mutation enum, runner injection,
IDOR/CSRF/JWT-specific mutation service, LLM shell access, a new LangGraph layer,
RLM integration without operating model, or new GDS algorithms without typed
projection contracts.

## Как начинать новый чат

Начать так:

```text
Вот архив проекта. Прочитай HANDOFF_FOR_NEW_CHAT.md, docs/architecture/current-state-sync.md, docs/architecture/research-operating-model.md и docs/architecture/graph-math-role.md. Не строй заново уже реализованные слои. Цель — experience-first research system: memory, evidence, deltas, structural signals, proposals and approved action lifecycle. Следующий patch должен сохранять границы: LangGraph пишет proposals, CLI tools запускаются только через ActionService, Neo4j/GDS даёт structural signals, PostgreSQL остаётся source of truth.
```


### bb projection overview

The `bb` CLI can now consume the read-only program projection overview without contacting Postgres, Neo4j, GDS, OpenSearch, or workers directly:

```bash
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
python -m bb_cli --program-id <uuid> projection overview --json
```

It renders latest Surface Map snapshot state, latest persisted component analysis, graph/search durable queue counts, pending action-experience proposal counts, freshness flags, and suggested operator commands. `projection plan` orders those commands into a read-only operator sequence. `projection run-step <step_id>` can preview or execute exactly one selected plan step through a fixed allow-list of canonical module commands (`python -m graph_projector`, `python -m search_indexer`, and read-only `python -m bb_cli` inspection commands); execution requires `--execute --yes` and uses `subprocess.run(..., shell=False)`. Preview and execute invocations append a bounded local JSONL audit event to `.bb/audit/projection-run-step.jsonl` unless `--no-audit` is passed; `--audit-log` can redirect it. `projection audit` is the read-only local audit viewer for that JSONL trail; `projection audit-summary` aggregates the same trail by operator step. It never invents commands, never submits actions, and never bypasses ActionService/policy.

- Credential references support runner-specific `auth_injection` metadata, including explicit CLI flags behind profile opt-in; raw secrets still stay out of action/proposal/agent payloads.

Credential lease service note: `CredentialLeaseService` is the application-level boundary for issuing/revoking/resolving credential leases. Stores are defensive persistence backends, not caller APIs for secret material.

Credential secret version lifecycle status after patch 0036:
`credential_refs.current_secret_version_id`, refresh metadata, and `credential_secret_versions.expires_at/replaced_by_version_id` exist. `CredentialSecretVersionService` rotates/marks expired secret versions behind stable credential refs. New leases select only the current active version. Refresh metadata is public scheduler metadata and must not contain raw secrets. `PostgresCredentialStore` now persists the registry/secret-version/lease metadata through SQLAlchemy Core and requires an explicit `SecretCodec`; tests/dev can opt into `DevOnlyPlaintextSecretCodec`, while production composition must provide encrypted/vault-backed encoding.

Credential materialization status after patch 0034:
`CredentialMaterializationPlan` exists as runner-side contract for leased secret material. It can describe argv additions, env additions, request headers/cookies/proxy metadata, and temp-file descriptors with redacted audit/log views. `CommandExecutor` now accepts env overlays through `CommandInvocation` and logs only env names. No concrete runner lease injection has been wired yet.


Patch 0038 added `LocalEncryptedSecretCodec`, an AES-256-GCM `SecretCodec` for encrypted Postgres secret blobs. It requires an injected 32-byte master key, supports `CREDENTIAL_MASTER_KEY` base64 loading, stores ciphertext/nonce/key metadata only, and reconstructs `SecretMaterial` only during lease resolution. `DevOnlyPlaintextSecretCodec` remains dev/test-only; external Vault/KMS codecs are still future adapters.

Patch 0039 added the credential backend composition boundary. `Settings` now has `CREDENTIAL_SECRET_BACKEND`, `CREDENTIAL_MASTER_KEY`, `CREDENTIAL_KEY_ID`, and `CREDENTIAL_ALLOW_DEV_PLAINTEXT`. `build_credential_secret_codec(...)` and `build_postgres_credential_store(...)` are the wiring point for `PostgresCredentialStore`; encrypted Postgres is the default, missing `CREDENTIAL_MASTER_KEY` fails closed, and `dev_plaintext` requires explicit opt-in with `CREDENTIAL_ALLOW_DEV_PLAINTEXT=true`.

Patch 0040 plan/status:
`CredentialManagementService` and `/api/v1/credentials` are the audit-safe boundary for creating stable identity refs, rotating secret versions, expiring the current version, and reading metadata. Rotation requests may contain raw secret material, but responses, logs, graph/search/read-models and agent state must only receive audit-safe views. This service does not resolve leases or materialize runner argv/env/temp files.

## Patch 0047 status

Completed: `0047_extract_action_read_and_run_state_stores`.

- `ActionReadStore` owns action read models: `list_actions`, `get_action`,
  `list_action_events`, `list_action_runs`, and `list_action_artifacts`.
- `RunStateStore` owns runner state transitions: `mark_run_started`,
  `mark_run_flushing`, `mark_run_finished`, `mark_run_needs_reconcile`, and
  `clear_run_reconcile`.
- `OrchestrationStore` remains a compatibility facade. New orchestration
  scenarios must not be added there.
- Approval request creation moved to neutral session-bound action write helpers,
  avoiding `ActionCommandStore -> approval_store.free_function` coupling.
- `EventStore.record_event` now swallows only duplicate event id integrity
  conflicts and re-raises other integrity failures.

Patch `0048_refactor_graph_projector_cli_entrypoint` completed.

- `graph_projector.__main__` is now a thin entrypoint only. It imports `main`
  from `cli_app` and exits with `main()` when executed as a module.
- CLI responsibilities moved to named owners: `cli_parser.py`, `cli_handlers.py`,
  `cli_operational_commands.py`, `cli_batch_commands.py`,
  `cli_surface_commands.py`, `cli_maintenance_commands.py`, `cli_services.py`,
  `cli_enqueuer_factory.py`, and `cli_output.py`.
- Existing command names and outputs were preserved. Old source-grep guards now
  read the full CLI source set instead of asserting that every command lives in
  `__main__.py`.
- Added `docs/architecture/graph-projector-cli-boundary.md` and a boundary test
  that prevents `__main__.py` from becoming an application again.

Patch `0049_fixup_graph_projector_cli_composition` completed.

- `GraphFactEnqueuerFactory` owns the repeated canonical enqueuer composition
  pattern: Postgres connection, `GraphFactBatchStore`, producer, worker id, lock
  seconds, and max attempts.
- `cli_batch_commands.py` keeps named command functions, but repeated enqueue
  once/loop mechanics now go through `_run_enqueue_once` and `_run_enqueue_loop`.
- The brittle `__main__.py` source guard no longer requires a specific parser
  import; it checks thin-entrypoint properties and forbidden runtime/parser
  tokens instead.
- `cli_services.py` remains a composition root, but new canonical producers
  should use the shared factory rather than copying builder bodies. Lazy imports
  remain a future startup cleanup.

Patch `0050_graph_algorithm_backlog_extraction` completed. It adds `docs/architecture/graph-algorithm-backlog.md`, updates navigation, and adds policy tests for graph backlog scope and parser/handler registry parity.

Patch `0051_typed_projection_contract_inventory` completed.

- `services/graph-projector/graph_projector/projection_contracts.py` is the machine-checkable typed projection contract source.
- `ProjectionContract` requires name, purpose, input facts, node types, edge types, allowed algorithms, output structural signals, lineage requirements, sensitivity rules, forbidden interpretations, failure modes, and `contract_only` status.
- Required contracts exist for `G_asset`, `G_http`, `G_identity`, `G_finding`, `G_temporal`, `G_bipartite_endpoint_param`, `G_bipartite_host_tech`, and `G_bipartite_endpoint_object`.
- `docs/architecture/typed-graph-projections.md` is the human review surface for the same inventory.
- `docs/architecture/g-http-projection-contract.md` — minimal `G_http` projection event/shape contract.
- `docs/architecture/bipartite-endpoint-param-contract.md` — minimal `G_bipartite_endpoint_param` endpoint ↔ param contract.
- This patch still does not build new projections, run GDS, create findings, or execute actions.

Patch `0052_typed_projection_contract_hardening` completed.

- The inventory is now described precisely as a machine-checkable shape inventory, not a full semantic graph contract system.
- `ProjectionContract` includes `contract_version`, `source_projections`, and bounded `AlgorithmFamily` enum values.
- Production constants now distinguish `EXPECTED_PROJECTION_CONTRACT_NAMES` from actual `PROJECTION_CONTRACT_NAMES`.
- Bipartite contracts declare machine-checkable dependencies on existing source projections.
- Future projection snapshots and structural signals must cite projection name plus `contract_version`.

Patch `0053_G_http_minimal_projection_contract` completed with fixup.

- `g_http_projection_contract.py` defines the `G_http` event/shape contract only; it does not build Neo4j projections, run GDS, create findings, or execute actions.
- Canonical source records are HTTP/inventory records only. Runs, action outcomes, and raw artifacts are lineage surfaces, not source records.
- Raw URL samples, query values, fragments, raw request/response bodies, header values, cookies, authorization values, and example/raw parameter values are forbidden payloads.
- Node key fields must be required, lineage, or explicit identity-only fields.
- Structural signals preserve projection name, `contract_version`, snapshot id, HTTP observation lineage, and evidence refs.

Patch `0054_G_bipartite_endpoint_param_baseline_contract` completed.

- `g_bipartite_endpoint_param_contract.py` defines a contract-only endpoint ↔ parameter projection shape layered on `G_http v1`.
- The projection has two nodes (`endpoint`, `param`), one edge (`HAS_PARAM`), and three structural signal contracts: `EndpointParamSimilaritySignal`, `ParamCentralitySignal`, and `MissingEndpointParamCandidateSignal`.
- The contract validates source projection refs, source `G_http` node/edge shape refs, key-field availability, lineage preservation, signal ↔ algorithm-family mapping, and forbidden raw parameter/URL payloads.
- Missing endpoint-param candidates are advisory structural signals only: not findings, not observed requests, and not permission to run tools.

Next recommended patch: `0055_G_bipartite_endpoint_param_projection_event_model`, still no GDS runtime; define the persisted structural signal event model or projection snapshot event envelope before building Cypher/GDS.


## Patch 0055 status

Next/active cleanup: `0055_structural_signal_event_model` introduces a contract-only StructuralSignal event/read-model boundary over G_http and G_bipartite_endpoint_param signals. Signals remain references + scores + lineage only; signal != finding and signal != action.

Patch `0056_hypothesis_from_structural_signal_contract` completed.

- Added `services/graph-projector/graph_projector/hypothesis_from_signal_contract.py`.
- Added `docs/architecture/hypothesis-from-structural-signal-contract.md`.
- The contract validates at import time and covers only `StructuralSignal -> HypothesisProposal`.
- It maps every current structural signal type exactly once to a proposal type.
- Proposal events carry refs, missing observations, confidence, priority, and review metadata only.
- Proposal events must not include findings, action proposals, approval requests, command invocations, raw payloads, exploit steps, command templates, or credential fields.

Next recommended patch: `0057_hypothesis_proposal_persistence_contract` or a focused critique/fixup of 0056 before persistence. Do not implement tool execution from hypotheses.
