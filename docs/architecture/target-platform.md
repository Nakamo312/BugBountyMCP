# Техническое задание: Bug Bounty Intelligence & Agent Workflow Platform
Целевая архитектура, execution layer, graph/search/RAG, agent-human workflow и roadmap — исправленная редакция 1.1

| **Параметр** | **Значение**                                                                                                                                                                                                                                                                                                                                                                                                           |
|--------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Статус       | Целевое техническое задание / архитектурный baseline / исправленная редакция                                                                                                                                                                                                                                                                                                                                           |
| Версия       | Версия 1.1                                                                                                                                                                                                                                                                                                                                                                                                             |
| Дата         | 11 июня 2026                                                                                                                                                                                                                                                                                                                                                                                                           |
| Назначение   | Описать финальную целевую архитектуру продукта, требования к подсистемам и порядок реализации.                                                                                                                                                                                                                                                                                                                         |
| Контекст     | Существующая система: рукописный pipeline через node representation, RabbitMQ как транспорт, PostgreSQL как источник истины, raw artifacts в файловом хранилище, OpenSearch projection. Целевая редакция уточняет: Neo4j является graph read model из GraphFacts, LangGraph является runtime для agent-human workflow, GDS/ML работает только по named projections, raw artifacts раскрываются LLM только по политике. |

Ограничение: платформа предназначена для автоматизации рутины bug bounty и authorized security research. Система не должна выполнять эксплуатацию, destructive fuzzing или state-changing тесты без явного scope/policy/approval workflow.

Редакция 1.1: уточнены границы Neo4j, LangGraph, RAG/raw access, GDS projections, OSINT/PII и статус agent types как workflow nodes/application services, а не отдельных микросервисов.

# Содержание

- 1. Цель и границы продукта

- 2. Исходное состояние и проблемы текущей системы

- 3. Целевая архитектура

- 4. Execution Plane и Tool Execution API

- 5. PostgreSQL schema для execution core

- 6. Transactional outbox и event model

- 7. Async protocol для AI/человека и agent notifications

- 8. Raw artifact store и Data Plane

- 9. OpenSearch Search Plane

- 10. Neo4j Security Knowledge Graph Read Model

- 11. Cypher Gateway и Graph Analyst Agent

- 12. RAG layer

- 13. LangGraph Agent + Human Workflow Plane

- 14. Tool/plugin architecture

- 15. Data collection roadmap

- 16. Agent analytics pipeline

- 17. Neo4j Graph Data Science и ML/Similarity

- 18. Dashboard и UI

- 19. Safety, governance, audit

- 20. Удаление research-engine

- 21. Acceptance criteria

- 22. Milestones и порядок внедрения

- 23. Итоговая схема

# 1. Цель и границы продукта

Цель проекта — построить платформу для bug bounty и authorized offensive security research, которая автоматизирует сбор, нормализацию, агрегацию, анализ и оформление результатов, но не превращается в автономный exploit framework.

Финальная версия продукта должна обеспечивать управляемый цикл: discovery → normalization → prioritization → bounded expansion → evidence → hypothesis → manual/agent workflow → report.

- единый запуск инструментов для человека, REST-клиента, MCP и LangGraph agents;

- поддержка разнородных источников данных: HTTP, DNS, ASN/CIDR, OSINT, технологии, зависимости, CVE, GitHub/GitLab, Docker Hub, cloud resources, buckets, CDN, certificates, JS, API schemas, mobile artifacts;

- нормализация результатов инструментов в canonical facts;

- построение Neo4j Security Knowledge Graph для связей между активами, технологиями, артефактами, гипотезами и findings;

- индексирование raw/sanitized артефактов в OpenSearch;

- хранение execution state, policy decisions, audit, metadata и reports в PostgreSQL;

- Agent + Human workflow через LangGraph с durable wait/resume и approval gates;

- единый dashboard для execution, graph, search, agents, findings, metrics и ручного запуска tools.

| **Плоскость**         | **Назначение**                                                                                                                                    | **Источник истины / runtime**               |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------|
| Execution Plane       | Запуск инструментов, очереди, leases, retries, statuses, raw artifact capture, policy enforcement.                                                | PostgreSQL + RabbitMQ + workers             |
| Data Plane            | Canonical metadata, normalized facts, raw artifact references, lineage.                                                                           | PostgreSQL + object/content-addressed store |
| Search Plane          | Поиск, retrieval, dashboard filtering, sanitized previews.                                                                                        | OpenSearch projection                       |
| Knowledge Graph Plane | Производная read model для связей между нормализованными GraphFacts: assets, web/API, technologies, OSINT, evidence paths, hypotheses и findings. | Neo4j projection / rebuildable read model   |
| Agent Workflow Plane  | Смысловые workflow между агентами и человеком.                                                                                                    | LangGraph + Agent Inbox + RAG               |

# 2. Исходное состояние и проблемы текущей системы

На текущий момент система является рукописным pipeline через node representation. RabbitMQ выполняет роль транспорта. События и статусы хранятся в PostgreSQL. Raw output tools хранится в файловой системе, а PostgreSQL хранит ссылки на raw artifacts и нормализованные факты, если они достаточно малы.

## 2.1 Текущие сильные стороны

- уже существует node/pipeline representation;

- RabbitMQ отделяет producer/consumer и снижает coupling между компонентами;

- есть таблицы и статусы для queued/running/leased/failed/completed;

- частично решена лавина событий через scheduler и формализацию задач в базе;

- PostgreSQL уже выполняет роль operational source of truth;

- есть REST API для запуска инструментов, который можно превратить в Tool Execution API;

- OpenSearch уже естественно подходит как search projection для raw/sanitized artifacts.

## 2.2 Критичные проблемы

| **Проблема**                    | **Описание**                                                                                                                     | **Требуемое решение**                                                                                 |
|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Субъективный execution chain    | Запуск доменного сканирования может автоматически тянуть http probing, port scanning, crawlers, JS analysis и downstream fanout. | Ввести bounded expansion, budgets, campaign lifecycle, explicit priorities и scheduler decisions.     |
| Event storm                     | Новые активы после ingest генерируют новые события, что может вызвать лавину jobs и agent reactions.                             | Dedup/work_key, coalescing, fanout limits, depth limits, token bucket, cooldown, campaign quiescence. |
| Options теряются                | Options проходят policy, но часто не доходят до runner.                                                                          | Ввести ToolInvocation contract и передавать typed options в runner.                                   |
| Scope enforcement не там        | Scope checks частично происходят на ingest/emit стадии, а не до создания job.                                                    | ScopePolicy должен срабатывать до job creation; ingest checks оставить defense-in-depth.              |
| Нет transactional outbox        | DB state и Rabbit publish не атомарны.                                                                                           | Ввести event_outbox в одной transaction с action/job/run.                                             |
| Raw artifacts растут            | Файловое хранение raw output создаёт проблемы объёма, дедупликации, retention, lineage.                                          | Content-addressed store, compression, retention policy, metadata в PostgreSQL.                        |
| research-engine нежизнеспособен | Отдельный сервис не должен оставаться псевдо-intelligence слоем.                                                                 | Удалить сервис; не переносить research-логику в ядро. Полезные идеи вернуть позже в LangGraph-ноды.   |

# 3. Целевая архитектура

Целевая архитектура строится вокруг чёткого разделения ответственности. LangGraph не заменяет execution scheduler. Neo4j не заменяет PostgreSQL. OpenSearch не заменяет Neo4j. Каждый компонент получает собственную роль.

```text
Human UI / REST / MCP / LangGraph Agents

|

v

Tool Execution API

|

v

ActionService + CapabilityPolicy + ScopePolicy + ApprovalPolicy

|

v

PostgreSQL transaction:

action_request

policy_decision

scope_decision

approval_state

job

run

event_outbox

|

v

Outbox Publisher

|

v

RabbitMQ

|

v

Workers / Runners

|

v

Raw Artifact Store

|

v

Parser -> Processor -> Ingestor

|

+--> PostgreSQL canonical facts

+--> OpenSearch search documents

+--> GraphFactBatch -> Neo4j projector

|

v

LangGraph reads:

PostgreSQL summaries

OpenSearch sanitized indexes

Neo4j read-only graph

RAG memory

|

v

Hypotheses -> Evidence -> Findings -> Reports
```

| **Компонент** | **Должен делать**                                                                                                                               | **Не должен делать**                                                                                                 |
|---------------|-------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| PostgreSQL    | Хранить execution state, policy decisions, metadata, canonical facts, audit.                                                                    | Хранить большие raw bodies как primary storage или имитировать полноценный graph engine.                             |
| RabbitMQ      | Передавать события между outbox publisher и consumers/workers.                                                                                  | Быть источником истины или state machine.                                                                            |
| OpenSearch    | Хранить search/retrieval projection, sanitized previews, dashboard filters.                                                                     | Быть canonical storage или graph database.                                                                           |
| Neo4j         | Хранить Security Knowledge Graph read model: normalized GraphFacts, relationships, paths, clusters, evidence graph, query-oriented projections. | Хранить raw tool outputs, большие raw bodies, run state, job lifecycle или произвольные JSON без GraphFact contract. |
| LangGraph     | Управлять semantic agent-human workflows, approvals, wait/resume, hypotheses, reports, tool-action intents.                                     | Напрямую запускать tools, писать в RabbitMQ, менять run statuses или обходить Tool Execution API.                    |

# 4. Execution Plane и Tool Execution API

Execution Plane должен стать независимым от потребителя. Один и тот же путь запуска используется человеком, REST client, MCP, LangGraph agent, scheduler и будущим CLI.

```text
Consumer

-> Tool Execution API

-> ActionService

-> CapabilityPolicy

-> ScopePolicy

-> ApprovalPolicy

-> OrchestrationStore

-> Outbox

-> RabbitMQ

-> Worker
```

## 4.1 ToolInvocation contract

Runner не должен получать только targets. Runner должен получать полный ToolInvocation с action/job/run identifiers, profile, safety level, options и policy/scope references.

```text
class ToolInvocation:

action_id: UUID

job_id: UUID

run_id: UUID

program_id: UUID

capability: str

profile: str

targets: list[str]

options: dict

safety_level: str

scope_decision_id: UUID

policy_decision_id: UUID

campaign_id: UUID

correlation_id: UUID
```

## 4.2 Обязательный порядок запуска

24. API принимает ToolActionRequest.

25. CapabilityPolicy проверяет capability/profile/options.

26. ScopePolicy проверяет targets against program scope.

27. RiskPolicy определяет safety level.

28. ApprovalPolicy определяет, нужен ли human approval.

29. Если approval не нужен, OrchestrationStore создаёт action/job/run/event_outbox в одной transaction.

30. OutboxPublisher публикует событие в RabbitMQ.

31. Worker получает событие, выполняет runner, пишет raw artifact, запускает parser/processor/ingestor.

# 5. PostgreSQL schema для execution core

PostgreSQL schema должна быть пересмотрена вокруг execution core, audit, artifacts metadata, normalized facts и agent coordination metadata.

| **Блок**           | **Таблицы**                                                                                                                               | **Назначение**                                                              |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| Capability Catalog | tool_capabilities, tool_profiles, tool_profile_options, tool_safety_classes, tool_input_schemas, tool_output_schemas                      | Описывает доступные tools, profiles, options, safety classes, output kinds. |
| Action Requests    | action_requests, action_request_targets, action_request_options, policy_decisions, scope_decisions, approval_requests, approval_decisions | Фиксирует запрос, policy/scope result, approval state и audit.              |
| Jobs/Runs          | jobs, tool_runs, node_runs, run_attempts, run_leases, run_errors, run_metrics                                                             | Отделяет логическую задачу от конкретной попытки исполнения.                |
| Outbox/Inbox       | event_outbox, event_inbox, event_store                                                                                                    | Обеспечивает atomic DB write + async event delivery + replay/idempotency.   |
| Artifacts          | raw_artifacts, artifact_blobs, artifact_previews, artifact_sanitized_previews, artifact_lineage, artifact_retention_policy                | Хранит metadata, ссылки, хэши, preview, sanitizer status, lineage.          |
| Agent Coordination | agent_workflows, agent_workflow_runs, agent_subscriptions, agent_inbox, agent_wait_conditions, agent_result_sets                          | Связывает LangGraph workflows с событиями execution/data/projections.       |

# 6. Transactional outbox и event model

Transactional outbox обязателен. Нельзя отдельно записать job/run в PostgreSQL и потом отдельно надеяться, что Rabbit publish пройдёт успешно.

```text
PostgreSQL transaction:

insert action_request

insert policy_decision

insert scope_decision

insert job

insert run

insert event_outbox(status='pending')

commit

OutboxPublisher:

SELECT pending FOR UPDATE SKIP LOCKED

publish RabbitMQ

mark published_at / attempts / last_error
```

## 6.1 Event taxonomy

| **Категория**       | **События**                                                                                                                                                   |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Execution           | action.accepted, action.rejected, action.waiting_for_approval, action.approved, job.queued, job.started, job.completed, run.leased, run.completed, run.failed |
| Artifact            | artifact.raw.created, artifact.raw.compressed, artifact.preview.created, artifact.preview.sanitized                                                           |
| Ingestion           | parser.started/completed/failed, processor.started/completed/failed, ingestor.started/completed/failed, facts.created, facts.updated                          |
| Projection          | opensearch.index.requested/indexed/index_failed, neo4j.projection.requested/projected/projection_failed                                                       |
| Discovery Expansion | asset.discovered, asset.normalized, asset.prioritized, expansion.requested/suppressed/scheduled/completed, campaign.quiescent                                 |
| Agent               | agent.workflow.started/waiting/resumed/completed/failed, agent.inbox.message_created, agent.hypothesis.created, agent.advisory_intent.created                 |

# 7. Async protocol для AI/человека и agent notifications

ToolActionRequest должен стать durable async protocol. Агент не может получить 200 OK и “понять”, что результат готов. API должен возвращать 202 Accepted с action/job/run/campaign/correlation identifiers и ссылками на ожидание, события и результаты.

```text
POST /tool-actions

-> 202 Accepted

{

action_id,

job_id,

initial_run_id,

campaign_id,

correlation_id,

workflow_id,

approval_required,

policy_decision_id,

scope_decision_id,

wait_url,

events_url,

result_url,

subscription_id

}
```

## 7.1 Correlation model

| **ID**         | **Назначение**                                                                                                                 |
|----------------|--------------------------------------------------------------------------------------------------------------------------------|
| action_id      | Исходный запрос человека или агента.                                                                                           |
| job_id         | Логическая задача, созданная из action.                                                                                        |
| run_id         | Конкретная попытка исполнения job.                                                                                             |
| campaign_id    | Группа связанных действий и downstream expansion.                                                                              |
| correlation_id | Идентификатор causality chain: workflow -\> action -\> job -\> run -\> artifact -\> facts -\> projections -\> downstream jobs. |
| workflow_id    | LangGraph workflow, если action создан агентом.                                                                                |

## 7.2 Agent subscriptions и inbox

Агенты не должны polling’ом читать все таблицы. Нужен durable notification layer: AgentEventRouter читает event_store, матчится с active subscriptions и создаёт сообщения в agent_inbox.

| EventStore -\> AgentEventRouter -\> AgentInbox -\> AgentScheduler -\> LangGraph resume |
|----------------------------------------------------------------------------------------|

| **Таблица**           | **Назначение**                                                                                                                   |
|-----------------------|----------------------------------------------------------------------------------------------------------------------------------|
| agent_subscriptions   | Описывает, какие события интересуют workflow или агенту: program_id, campaign_id, correlation_id, event_types, entity_selectors. |
| agent_inbox           | Durable очередь сообщений для агентов. Хранит event_id, workflow_id, agent_id, status, delivered_at, acked_at.                   |
| agent_wait_conditions | Описывает, чего LangGraph workflow ждёт.                                                                                         |
| agent_result_sets     | Стабильная ссылка на набор результатов, появившихся из action/campaign/workflow.                                                 |

## 7.3 Wait conditions

| **Condition**       | **Когда использовать**                                                                                                                                                   |
|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| tool_run_completed  | Ждать завершения конкретного run.                                                                                                                                        |
| ingestion_completed | Ждать завершения parser/processor/ingestor по action.                                                                                                                    |
| projections_ready   | Ждать, пока PostgreSQL facts, OpenSearch и Neo4j догнали нужный watermark.                                                                                               |
| new_facts_available | Ждать появления фактов определённого типа: Endpoint, Technology, CVE, Secret и т.д.                                                                                      |
| campaign_quiescent  | Ждать стабилизации discovery chain: нет queued/running jobs, unpublished outbox events, unprocessed ingestion events, projection lag и новых events в quiescence window. |

## 7.4 Campaign lifecycle

- created

- running

- expanding

- waiting_for_projections

- quiescent

- closed

- cancelled

- failed

Важно: campaign.quiescent не означает, что программа полностью изучена. Это значит, что текущая discovery chain закончила обработку всех известных событий в рамках budget и policy.

# 8. Raw artifact store и Data Plane

Raw artifact store должен перейти от ad-hoc файлового хранения к content-addressed storage. PostgreSQL хранит metadata и ссылки, но не большие тела.

| **Требование**            | **Описание**                                                                                                                                                                                                  |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Content-addressed storage | Хранение по sha256/blake3 с дедупликацией.                                                                                                                                                                    |
| Compression               | Большие raw outputs, HTTP bodies, JSONL и logs должны сжиматься.                                                                                                                                              |
| Retention policy          | Разные retention classes для logs, bodies, screenshots, secrets, previews.                                                                                                                                    |
| Sanitized previews        | Для OpenSearch и LLM exposure используется sanitized preview.                                                                                                                                                 |
| Lineage                   | Каждый artifact связан с tool_run, parser version, sanitizer version, source target и scope decision.                                                                                                         |
| Safety flags              | raw_safe_for_llm=false по умолчанию; sanitized_safe_for_llm=true только после sanitizer. external_llm_allowed=false по умолчанию для raw artifacts.                                                           |
| Controlled raw access     | Raw artifact retrieval для агента возможен только по artifact_id/result_set_id, с workflow_id, policy decision, audit event, sensitivity class и явным режимом доступа: sanitized, restricted_raw, local_raw. |

| **Normalized facts**    | **Примеры**                                                                    |
|-------------------------|--------------------------------------------------------------------------------|
| Infrastructure          | organizations, domains, hosts, ip_addresses, cidrs, asns, services             |
| Web/API                 | urls, endpoints, parameters, headers, cookies, http_observations               |
| Technology              | technologies, technology_versions, frameworks, packages, package_versions      |
| Vulnerability knowledge | cves, cwes, templates, misconfig_signals, findings                             |
| OSINT                   | repositories, commits, emails, persons, cloud_resources, buckets, certificates |
| Research                | hypotheses, evidence_items, advisory_intents, reports                          |

# 9. OpenSearch Search Plane

OpenSearch является rebuildable search projection. Он нужен для поиска по raw/sanitized artifacts, dashboard filters, retrieval и agent-facing sanitized indexes.

| **Индекс**           | **Назначение**                                                       |
|----------------------|----------------------------------------------------------------------|
| bb-artifacts-preview | Sanitized previews raw artifacts.                                    |
| bb-http-observations | HTTP observations, headers, status, content type, selected preview.  |
| bb-tool-logs         | stdout/stderr/tool execution logs.                                   |
| bb-endpoints         | Endpoints, params, methods, normalized paths.                        |
| bb-technologies      | Detected technologies/frameworks/versions.                           |
| bb-packages          | Packages, dependencies, versions.                                    |
| bb-cves              | CVE metadata and relevance summaries.                                |
| bb-osint-entities    | OSINT entities: repos, emails, persons, orgs, certificates, buckets. |
| bb-secrets           | Redacted secret findings and credential hints.                       |
| bb-hypotheses        | Hypotheses and status.                                               |
| bb-findings          | Findings, severity, evidence refs.                                   |
| bb-agent-events      | Agent events, decisions, workflow summaries.                         |

Требования: schema versioning, replayable indexing, sanitizer version, per-program filtering, retention, redaction tokens, index lag metrics.

# 10. Neo4j Security Knowledge Graph Read Model

Neo4j используется как Security Knowledge Graph read model из нормализованных GraphFacts. Граф нужен не для хранения raw output и не для произвольной свалки JSON, а для query-oriented связей между активами, HTTP/API поверхностью, технологиями, зависимостями, CVE, OSINT, cloud, secrets, hypotheses, evidence и findings. Любая связь в Neo4j должна быть производной, пересобираемой и привязанной к source_artifact_id/tool_run_id/confidence.

Жёсткое ограничение: Neo4j не является source of truth. При потере Neo4j граф должен пересобираться из PostgreSQL canonical facts, event log, GraphFactBatch и raw artifact metadata. Raw bodies, stdout/stderr, HAR целиком, screenshots и большие документы остаются в raw artifact store.

## 10.1 GraphFact contract

```text
class GraphNodeFact:

kind: str

key: str

properties: dict

confidence: float

source_artifact_id: UUID

tool_run_id: UUID

class GraphEdgeFact:

src_kind: str

src_key: str

edge_kind: str

dst_kind: str

dst_key: str

properties: dict

confidence: float

source_artifact_id: UUID

tool_run_id: UUID

class GraphFactBatch:

program_id: UUID

facts: list[GraphNodeFact | GraphEdgeFact]

produced_by: str

parser_version: str
```

## 10.2 Принцип планирования графовой онтологии

Список labels и relationship types не фиксируется произвольно. Онтология Neo4j должна выводиться из источников данных, parser outputs, query patterns, agent workflows и требований к evidence. Любой новый label проходит через graph node card и попадает в одну из стадий зрелости: candidate, experimental, stable, deprecated.

- Source-driven: узел или связь добавляется только если есть конкретные источники данных и parser/processor, которые стабильно порождают этот факт.

- Query-driven: сущность выделяется в отдельный узел только если по ней планируются path queries, clustering, similarity, aggregation, linking с CVE/OSINT/evidence или agent reasoning.

- Evidence-backed: каждая связь должна иметь source_artifact_id, tool_run_id, confidence, first_seen, last_seen, scope_status и при необходимости manual_verified.

- Lifecycle-aware: временные и шумные признаки сначала попадают в Observation/Artifact properties. В stable graph они повышаются только после повторяемости или ценности для queries.

- Minimal-core-first: сначала проектируется небольшой L0/L1 graph backbone, затем добавляются domain packs: Web/API, OSINT, Supply Chain, Cloud, Secrets, Research.

- Property-vs-node rule: значение становится узлом только если оно связано с несколькими сущностями, имеет собственный lifecycle или участвует в path queries. Иначе это property.

## 10.3 Методика вывода узлов и связей

32. Зафиксировать источники данных: конкретные tools, API adapters, imports и manual artifacts.

33. Для каждого источника описать raw artifact kind, parser output, normalized facts и confidence model.

34. Для каждого normalized fact решить: это node, relationship, property или Observation.

35. Для каждого node определить identity key: например Host.fqdn, IP.address, Service.host+port+protocol, Endpoint.service+method+normalized_path, Package.ecosystem+name.

36. Для каждой связи определить направление, cardinality, source evidence, confidence update policy и stale policy.

37. Для каждой сущности определить минимум один query/use case. Если use case отсутствует, label не добавляется в stable ontology.

38. Для каждого label завести graph node card: назначение, источники, ключ, обязательные свойства, связи, retention, PII/sensitivity, примеры запросов.

## 10.4 План онтологии по уровням зрелости

Ниже перечислены не окончательные labels, а план расширения. Stable schema должна расти по слоям. Каждый слой вводится только после готовности parser outputs, tests и query templates.

- L0 Core / Evidence backbone: Program, Scope, Tool, ToolRun, Artifact, Observation, Evidence. Эти сущности нужны для lineage и воспроизводимости.

- L1 Infrastructure backbone: Domain, Host, IP, ASN, CIDR, Service. Источники: subfinder/amass/dnsx/naabu/httpx/RDAP/certificates. Основные связи: HAS_SCOPE, MATCHES_SCOPE, RESOLVES_TO, IN_CIDR, ANNOUNCED_BY, EXPOSES_SERVICE.

- L2 Web/API layer: URL, Endpoint, Parameter, HeaderName, CookieName, JSFile, APISchema. Header/Cookie values не являются узлами по умолчанию; они хранятся как свойства Observation или sanitized artifact preview. Узлом становится имя/тип, если оно участвует в cross-endpoint analysis.

- L3 Technology and Supply Chain layer: Technology, Framework, Package, PackageVersion, SourceRepo, Commit, CVE, CWE, Template. Dependency чаще является relationship DEPENDS_ON, а не отдельным узлом. Отдельный Dependency node допускается только если нужен lifecycle dependency record с metadata.

- L4 OSINT / Cloud / Exposure layer: Organization, Brand, CloudAccount, CloudResource, Bucket, CDN, Secret, CredentialHint. Person и Email являются restricted/optional labels и включаются только при явной OSINT-задаче, PII policy и sanitization controls.

- L5 Research layer: Hypothesis, Finding, Report. Hypothesis не равен finding. Finding создаётся только после evidence chain и manual/critic verification workflow.

## 10.5 Правила promotion/demotion

- Candidate label: найден полезный тип факта, но нет стабильного parser output или query template.

- Experimental label: есть parser output и несколько queries, но нет достаточных тестов и стабильной identity key.

- Stable label: есть identity key, constraints, graph facts, tests, query templates, rebuild support и dashboard/search representation.

- Deprecated label: label оказался property/relationship, дублирует другой label или не используется в queries. Требуется migration path.

- Promotion запрещён без acceptance criteria: как минимум один source, один producer, один query, один тест idempotent upsert, один пример evidence lineage.

## 10.6 Query templates

- hidden endpoints from JS;

- endpoint neighborhood;

- exposed services by technology;

- CVE to exposed service paths;

- package to endpoint paths;

- ASN/CIDR asset expansion;

- cloud resource exposure paths;

- secrets to repository/domain paths;

- hypothesis evidence paths;

- finding blast radius;

- similar endpoints/services/technology stacks;

- stale assets and newly discovered high-value paths.

## 10.7 Правила Graph Data Science projections

Neo4j GDS и ML/similarity алгоритмы запрещено запускать по всему Security Knowledge Graph без явной проекции. Каждый алгоритм получает named projection с описанными node labels, relationship types, relationship weights, orientation, filters, expected output и use case.

Проекция должна отвечать на один конкретный вопрос: endpoint similarity, asset exposure, CVE exposure path, OSINT-to-asset path, secret-to-asset path, hypothesis/evidence path или business-flow/state relation. Если вопрос не сформулирован, projection не создаётся.

- GDS projection не должна смешивать несопоставимые сущности без query/use case.

- Результаты GDS являются derived signals, а не canonical facts.

- Любой derived cluster/similarity/path должен ссылаться на projection version и исходные graph facts.

- Community detection, embeddings и link prediction относятся к M8 Advanced analytics, а не к M4 graph backbone.

# 11. Cypher Gateway и Graph Analyst Agent

Graph Analyst Agent должен уметь выполнять не только template queries, но и произвольный read-only Cypher. Но он не должен подключаться напрямую к Neo4j. Все запросы идут через Cypher Gateway.

```text
Graph Analyst Agent / UI

-> Cypher Gateway

-> AST validation

-> read-only policy

-> program boundary check

-> timeout/limit injection

-> EXPLAIN/preflight

-> audit

-> Neo4j read-only user

-> Result Shaper

-> compact summary + query_result_id
```

| **Требование**        | **Описание**                                                                       |
|-----------------------|------------------------------------------------------------------------------------|
| Read-only Neo4j user  | Gateway использует пользователя без write privileges.                              |
| AST validation        | Блокируются CREATE, MERGE, SET, DELETE, REMOVE, LOAD CSV, DROP, system operations. |
| Procedure allowlist   | CALL по умолчанию запрещён; разрешаются только безопасные read-only procedures.    |
| Timeout               | default_timeout_ms=3000; max_timeout_ms=15000.                                     |
| Row limit             | default_limit=100; max_limit=1000; LIMIT добавляется, если отсутствует.            |
| Program isolation     | Каждый запрос ограничивается program_id.                                           |
| Parameterized queries | Запрещена строковая склейка значений.                                              |
| Explain/preflight     | validate_only, explain, execute modes.                                             |
| Audit                 | query_text/hash, params_hash, agent_id, workflow_id, timing, rows, errors.         |
| Result shaping        | Raw rows сохраняются ссылкой; LLM получает compact summary.                        |

## 11.1 Safety classes для arbitrary read-only Cypher

| **Класс**      | **Условия**                                                                            | **Решение**                               |
|----------------|----------------------------------------------------------------------------------------|-------------------------------------------|
| Safe read      | program_id boundary, LIMIT \<= 100, depth \<= 3, no CALL, timeout \<= 3s.              | Разрешить без approval.                   |
| Expensive read | variable path, depth 4-8, LIMIT \<= 1000, GDS stream procedure, timeout \<= 15s.       | Budget check или human approval.          |
| Dangerous read | unbounded traversal, no program boundary, CALL outside allowlist, cross-program query. | Блокировать или требовать admin approval. |

# 12. RAG layer

RAG должен быть scoped и сегментированным. Не должно быть одного общего индекса, куда попадает всё подряд.

| **Retrieval space** | **Содержимое**                                                                                   |
|---------------------|--------------------------------------------------------------------------------------------------|
| Program RAG         | scope rules, policy, forbidden actions, previous reports, platform rules.                        |
| Methodology RAG     | чеклисты, internal methodology, bug class playbooks, report templates.                           |
| Artifact RAG        | sanitized previews, parsed API schemas, JS routes, code snippets.                                |
| Graph RAG           | graph neighborhoods converted to text, paths, evidence chains, hypothesis contexts.              |
| Agent Memory        | previous decisions, rejected hypotheses, false positives, user notes, manual verification notes. |

RAG не должен отдавать raw secrets, cookies, tokens, PII или небезопасные response bodies внешним LLM без sanitizer и explicit permission. Для локального/trusted model режима допускается controlled raw access только через policy, audit, scoped artifact retrieval, sensitivity flags и workflow-level permission.

# 13. LangGraph Agent + Human Workflow Plane

LangGraph отвечает за semantic tasks, а не за низкоуровневый lifecycle tool runs. Единица LangGraph workflow — задача шире одного запуска инструмента.

| **Semantic task**             | **Пример**                                                       |
|-------------------------------|------------------------------------------------------------------|
| Оценить поверхность программы | Прочитать новые факты, граф, search results и выделить gaps.     |
| Найти CVE exposure paths      | Связать technologies/packages/versions/CVE/exposed services.     |
| Построить гипотезы            | Создать evidence-linked hypotheses по graph/search/RAG.          |
| Подготовить проверку          | Сформировать ToolActionRequest или manual checklist.             |
| Собрать отчёт                 | Собрать evidence chain, reproduction steps, impact, remediation. |

## 13.1 Agent types

Важно: перечисленные Agent / Node являются LangGraph nodes и/или application services внутри Agent Workflow Plane. Они не являются отдельными микросервисами по умолчанию. Выделение в отдельный сервис допускается только при наличии отдельного lifecycle, scaling profile, storage boundary и тестируемого API contract.

| **Agent / Node**          | **Функция**                                                                             |
|---------------------------|-----------------------------------------------------------------------------------------|
| Recon Planner             | Анализирует gaps, предлагает следующий сбор данных, создаёт ToolActionRequest.          |
| Artifact Analyst          | Суммаризирует новые artifacts, выделяет interesting facts.                              |
| Graph Analyst             | Использует Neo4j templates и arbitrary read-only Cypher через Gateway.                  |
| Technology/CVE Agent      | Связывает technologies/packages/versions/CVE и exposed services.                        |
| Misconfiguration Agent    | Ищет misconfig candidates по graph/search/rules.                                        |
| Business Logic Agent      | Строит гипотезы по flows, roles, endpoints, state transitions.                          |
| Metamorphic Testing Agent | Строит варианты эквивалентных запросов/сценариев; требует scope/approval.               |
| Mutation Fuzzing Agent    | Предлагает mutation strategies; active запуск только через bounded profiles и approval. |
| Hypothesis Builder        | Создаёт hypotheses, связывает с evidence, выставляет confidence.                        |
| Critic/Verifier           | Проверяет scope, evidence, unsupported claims, false positives.                         |
| Report Builder            | Собирает report draft и sanitized reproduction steps.                                   |

## 13.2 LangGraph state

```text
class AgentWorkflowState:

workflow_id: UUID

program_id: UUID

objective: str

current_phase: str

campaign_id: UUID | None

action_ids: list[UUID]

subscription_ids: list[UUID]

pending_wait_condition_id: UUID | None

result_set_ids: list[UUID]

artifact_ids: list[UUID]

graph_node_refs: list[str]

graph_path_refs: list[str]

opensearch_query_refs: list[UUID]

cypher_query_result_ids: list[UUID]

hypothesis_ids: list[UUID]

finding_ids: list[UUID]

proposed_action_ids: list[UUID]

approval_request_id: UUID | None

risk_level: str | None

errors: list[str]
```

# 14. Tool/plugin architecture

Добавление новых tools должно быть дешёвым и безопасным. Каждый tool описывается manifest, adapter и тестами.

```text
id: httpx

kind: web_probe

safety_class: passive

input_schema: ...

options_schema: ...

output_artifact_kinds:

- httpx_jsonl

produces_facts:

- Host

- Service

- Technology

- URL

- HTTPObservation

produces_graph_facts:

- Host

- Service

- Technology

produces_search_documents:

- bb-http-observations

default_profile: passive

profiles:

passive:

max_targets: 1000

rate_limit: 50

conservative:

max_targets: 100

rate_limit: 10
```

- runner должен принимать ToolInvocation;

- parser превращает raw output в structured records;

- processor нормализует и обогащает records;

- ingestor пишет canonical facts;

- graph fact producer создаёт GraphFactBatch;

- search document producer создаёт OpenSearch documents;

- каждый adapter имеет option propagation tests, scope tests, parser tests, idempotency tests.

# 15. Data collection roadmap

| **Фаза**                             | **Инструменты / направления**                                                                                                                                                                    | **Ожидаемые факты**                                                                                                                                          |
|--------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Phase 1: Web backbone                | subfinder, dnsx, httpx, naabu, katana, gau/wayback, linkfinder, nuclei, wappalyzer.                                                                                                              | Domain, Host, IP, Service, URL, Endpoint, Parameter, Technology, TemplateFinding.                                                                            |
| Phase 2: Technology & supply chain   | JS dependency extraction, package-lock/yarn-lock/pnpm-lock, npm/pypi/maven/go modules, retirejs, SBOM parsers, CVE enrichment.                                                                   | Package, Version, Dependency, CVE, CWE, affected technology paths.                                                                                           |
| Phase 3: OSINT & infrastructure      | ASN/CIDR, RDAP/WHOIS, certificates/SAN, Shodan/Censys adapters, GitHub/GitLab search, Docker Hub, buckets, CDN. emails/person/org metadata — только restricted/explicit OSINT mode с PII policy. | Organization, ASN, CIDR, Certificate, Repo, SecretHint, CloudResource, Bucket. Person/Email — restricted optional facts, не включаются в default collection. |
| Phase 4: API & application semantics | OpenAPI parser, GraphQL parser, Postman collections, HAR/Burp import, auth/session role observations, APK static extraction.                                                                     | Schema, Endpoint, Mutation, RoleObservation, MobileApp, CredentialHint.                                                                                      |

# 16. Agent analytics pipeline

Конечный analytics pipeline должен поддерживать несколько типов анализа. Не всё должно быть отдельным LLM-агентом: часть узлов может быть deterministic scripts, classifiers, regressors, graph algorithms или rule engines.

| **Аналитический слой**     | **Назначение**                                                                            | **Требования к безопасности**                                      |
|----------------------------|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| Metamorphic testing        | Построение вариантов эквивалентных запросов/сценариев и сравнение инвариантов.            | Только в scope, bounded profiles, approval для state-changing.     |
| Mutation fuzzing           | AI-assisted mutation strategies для параметров, payload families, headers, content types. | Rate limits, max mutations, approval для active/destructive tests. |
| Hypothesis building        | Генерация hypotheses с evidence refs, confidence, required manual checks.                 | Hypothesis не равен finding.                                       |
| Technology/CVE analytics   | Связь technologies/packages/versions/CVE с exposed services.                              | Только evidence-linked conclusions.                                |
| Misconfiguration analytics | Поиск CORS, headers, cloud, bucket, TLS, CDN, auth misconfig candidates.                  | Нельзя автоматически повышать severity без verifier.               |
| Business logic analytics   | Flows, roles, state transitions, object ownership, IDOR/BAC candidates.                   | Требует human validation и controlled tests.                       |

# 17. Neo4j Graph Data Science и ML/Similarity

Neo4j GDS и отдельные ML/similarity алгоритмы используются только на именованных task-specific projections. Они применяются для кластеризации, поиска похожести, hidden paths, graph embeddings и приоритизации, но не являются частью canonical graph backbone и не должны выполняться по всему графу без projection contract.

| **Projection**                     | **Назначение**                                                                                                                                   |
|------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| Asset exposure projection          | Связи Program/Scope/Host/IP/Service/Endpoint.                                                                                                    |
| Endpoint similarity projection     | Похожие endpoints по path/template/params/status/response fingerprints.                                                                          |
| Technology/CVE exposure projection | Paths от technologies/packages/versions до exposed services.                                                                                     |
| OSINT-to-asset projection          | Связи от repos/emails/certificates/org metadata до assets.                                                                                       |
| Secret-to-asset projection         | Связи от secret hints до repos/cloud/resources/domains.                                                                                          |
| Hypothesis/evidence projection     | Связи hypotheses, observations, artifacts, findings.                                                                                             |
| Business-flow projection           | Flow/state/role relations.                                                                                                                       |
| Projection contract                | Для каждой GDS/ML projection фиксируются node labels, relationship types, weights, filters, version, expected output, use case и rebuild policy. |

| **Алгоритм**                    | **Use case**                                   |
|---------------------------------|------------------------------------------------|
| Community detection             | Кластеры assets/endpoints/services.            |
| Node similarity                 | Похожие endpoints/services/technologies.       |
| Shortest path                   | Связь OSINT/CVE/secret до exposed asset.       |
| Centrality                      | High-value nodes и приоритизация.              |
| Weakly connected components     | Группы связанных assets.                       |
| Graph embeddings                | Graph similarity и candidate ranking.          |
| Link prediction                 | Скрытые связи.                                 |
| SimHash/MinHash                 | Похожие URLs/responses/JS chunks.              |
| Response fingerprint clustering | Кластеры похожих HTTP responses.               |
| Endpoint template clustering    | Нормализация и группировка endpoint templates. |

# 18. Dashboard и UI

Нужен единый dashboard вместо набора разрозненных UI. Встроенные UI отдельных компонентов допустимы для debug/admin, но пользовательский рабочий интерфейс должен быть единым.

| **Раздел**       | **Функции**                                                                                |
|------------------|--------------------------------------------------------------------------------------------|
| Programs         | scope, rules, targets, risk settings.                                                      |
| Execution        | actions, jobs, runs, queues, leases, failures, retries, event storm metrics.               |
| Tools            | manual launch, profiles, options, safety class, dry-run, approval state.                   |
| Artifacts        | raw metadata, sanitized previews, lineage, retention.                                      |
| Search           | OpenSearch views, saved searches, filters.                                                 |
| Graph            | Neo4j graph viewer, query templates, Cypher Gateway UI, path explorer, clusters.           |
| Agents           | LangGraph workflows, agent state, pending approvals, decisions, traces, outputs.           |
| Hypotheses       | candidates, evidence, confidence, status, manual checks.                                   |
| Findings/Reports | drafts, evidence chain, reproduction steps, sanitized export.                              |
| Metrics          | ingestion rate, event rate, queue depth, artifact growth, projection lags, agent duration. |

# 19. Safety, governance, audit

- LLM never executes tools directly.

- LLM never writes directly to RabbitMQ.

- LLM never bypasses PolicyService.

- LLM never bypasses ScopePolicyService.

- All active actions require explicit profile and approval policy.

- All state-changing tests require human approval.

- External LLM access uses sanitized artifacts by default; raw artifact exposure requires explicit policy, audit, scoped retrieval and trusted/local model mode.

- Secrets/tokens/cookies/PII must be redacted by default for search indexes, reports and external LLM exposure.

- Cypher sandbox is read-only and audited.

- OpenSearch agent access uses sanitized indexes by default.

- Tool options are typed and allowlisted.

- Dangerous option keys are blocked.

- Every finding must link to evidence.

- Every graph edge should link to source artifact/run or confidence source.

- Every agent decision should be traceable to inputs, graph/search queries and evidence.

# 20. Удаление research-engine

Текущий research-engine считается нежизнеспособным как отдельный сервис и подлежит удалению. Ядро проекта не должно становиться research-слоем; гипотезы, critic/verifier и отчётные черновики относятся к будущим LangGraph-нодам.

| **Перенести**                 | **Куда**                                                 |
|-------------------------------|----------------------------------------------------------|
| sanitizer/redaction functions | Data Plane / Artifact sanitizer service                  |
| hypothesis data models        | будущие LangGraph-ноды, не ядро проекта                  |
| evidence data models          | будущие LangGraph-ноды, не ядро проекта                  |
| gatekeeper/critic ideas       | Critic/Verifier LangGraph node                           |
| safe LLM input/output schemas | Agent Workflow Plane schemas                             |
| confidence scoring functions  | Hypothesis Builder / ranking service, если не фикстуры   |

Исследовательская логика не входит в ядро проекта. Гипотезы, проверка, сбор отчётного черновика и связанные модели должны появляться позже внутри LangGraph-нод, а не как службы ядра.

# 21. Acceptance criteria

| **Область**              | **Критерии приёмки**                                                                                                                                                                           |
|--------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Execution Core           | options reach runner; scope before job creation; transactional outbox; event replay; idempotent workers; event storm controls; content-addressed raw artifacts; retention policy.              |
| Async Agent Protocol     | ToolActionRequest returns 202; action/job/run/campaign/correlation ids; wait conditions; agent inbox; result sets; LangGraph pause/resume.                                                     |
| Data Plane               | raw artifacts deduplicated; large bodies compressed; sanitized previews; lineage; parser/processor/ingestor versions tracked.                                                                  |
| OpenSearch               | versioned indexes; sanitized agent-facing indexes; replayable indexing; dashboard search; projection lag metrics.                                                                              |
| Neo4j                    | GraphFact contract; projector; first 5 tools produce graph facts; query templates; graph rebuild; graph paths link to artifacts; ontology labels have node cards and maturity state.           |
| Cypher Gateway           | arbitrary read-only Cypher; write clauses blocked; program boundary; timeout; row limit; procedure allowlist; audit; result shaping.                                                           |
| Agent Plane              | LangGraph reads graph/search/context; creates ToolActionRequest only via API; human approval; Hypothesis Builder; Critic; Report Builder.                                                      |
| Dashboard                | manual tool launch; queue/run status; graph explorer; pending approvals; hypotheses/evidence; report draft flow.                                                                               |
| Advanced analytics / GDS | GDS runs only on named projections; projection contract exists; results are derived signals; projection version and source graph facts are recorded; no full-graph mixed-semantics algorithms. |

# 22. Milestones и порядок внедрения

| **Milestone**                | **Работы**                                                                                                                                                | **Результат**                                        |
|------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------|
| M1: Stabilize execution core | Redesign execution schema; ToolInvocation; options propagation; scope before job; transactional outbox; event storm controls; tests.                      | Надёжный execution runtime.                          |
| M2: Artifact storage cleanup | Отложено за MVP; в MVP остаётся существующее хранение raw artifacts без новой архитектуры дедупликации/retention.                                         | Raw artifacts остаются ссылочным первичным материалом. |
| M3: Remove research-engine   | Delete service; do not move research logic into the core. LangGraph will own hypothesis/critic/report workflows later.                                    | Ядро освобождено от тупиковой research-службы.        |
| M4: Neo4j graph projection   | GraphFact contract; Neo4j repo/projector; subfinder/dnsx/httpx/katana/nuclei projections; graph rebuild; node cards and maturity policy for first labels. | Security Knowledge Graph backbone.                   |
| M5: OpenSearch expansion     | Missing indexes; replay indexer; sanitized indexes; dashboard views.                                                                                      | Search Plane готов для UI/agents.                    |
| M6: Async agent protocol     | agent_subscriptions; agent_inbox; wait_conditions; result_sets; campaign lifecycle; AgentEventRouter.                                                     | LangGraph может ждать и возобновляться.              |
| M7: LangGraph workflows      | Graph/search tools; ToolActionRequest tool; approval node; Hypothesis Builder; Critic; Report Builder.                                                    | Agent + Human Workflow Plane.                        |
| M8: Advanced analytics       | CVE paths; endpoint similarity; hidden paths; misconfig candidates; business logic workflows; metamorphic/mutation testing; named GDS projections only.   | Интеллектуальная аналитика поверх graph/search/RAG.  |
| M9: Unified dashboard        | Execution, Tools, Artifacts, Search, Graph, Agents, Hypotheses, Reports, Metrics.                                                                         | Единый рабочий интерфейс.                            |

# 23. Итоговая схема

```text
Discovery event does not directly mean "run all tools".

Correct model:

raw discovery

-> raw artifact

-> parser

-> normalized fact

-> search document

-> graph fact

-> prioritization

-> bounded expansion

-> hypothesis

-> evidence

-> manual/agent workflow

Core rule:

Scheduler owns tool execution lifecycle.

LangGraph owns semantic agent-human workflow.

Neo4j owns security knowledge graph.

OpenSearch owns search/retrieval projection.

PostgreSQL owns canonical operational state.
```

Финальная система должна исключить субъективную лавину событий. Каждый новый найденный asset создаёт normalized fact и graph fact. Дальше scheduler/agent/planner решает, что запускать, с каким бюджетом, с каким risk profile и под каким approval policy.

# Приложение A. Минимальный test plan

- test_policy_blocks_forbidden_options;

- test_policy_requires_approval_for_active_profile;

- test_action_scope_blocks_out_of_scope_active_target;

- test_scan_node_passes_options_to_runner;

- test_event_outbox_retries_publish_failure;

- test_node_registry_deduplicates_scheduled_work_key;

- test_raw_artifact_recorded_before_parse;

- test_opensearch_sanitizes_cookie_authorization;

- test_graph_fact_projection_is_idempotent;

- test_agent_waits_for_projections_ready;

- test_campaign_quiescent_requires_no_pending_jobs_and_no_projection_lag;

- test_cypher_gateway_blocks_write_clause;

- test_cypher_gateway_enforces_program_boundary;

- test_cypher_gateway_adds_limit_and_timeout;

- test_research_rejects_unsafe_evidence;

- test_llm_raw_artifact_requires_explicit_policy;

- test_graph_label_requires_node_card_and_query_use_case;

- test_gds_requires_named_projection_contract;

- test_agent_types_are_workflow_nodes_not_services_by_default;

- test_osint_person_email_disabled_by_default.

# Приложение B. Термины

| **Термин**            | **Определение**                                                                                                                                                             |
|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ToolActionRequest     | Формализованный запрос на запуск инструмента от человека, агента или scheduler.                                                                                             |
| Campaign              | Группа связанных действий и downstream expansion в рамках одной discovery chain.                                                                                            |
| Correlation ID        | Идентификатор причинно-следственной цепочки событий.                                                                                                                        |
| GraphFact             | Нормализованный node/edge fact для Neo4j read model. Каждый GraphFact имеет identity key, properties, confidence, source_artifact_id/tool_run_id и producer/parser version. |
| Result Set            | Стабильная ссылка на результаты action/campaign/workflow.                                                                                                                   |
| Wait Condition        | Durable условие, по которому LangGraph workflow приостанавливается и возобновляется.                                                                                        |
| Cypher Gateway        | Единая безопасная точка выполнения read-only Cypher для агентов и UI.                                                                                                       |
| Quiescence            | Состояние, когда текущая campaign не имеет активных jobs/events/projection lag в заданном окне.                                                                             |
| Named GDS Projection  | Именованный task-specific граф для Neo4j GDS/ML: фиксирует node labels, relationship types, weights, filters, version, use case и rebuild policy.                           |
| Controlled raw access | Политически ограниченный доступ агента/модели к raw artifact по artifact_id/result_set_id с audit, sensitivity class, explicit permission и выбранным режимом доступа.      |
