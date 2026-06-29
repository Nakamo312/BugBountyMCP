# Research Operating Model

Status: baseline for patches after `0040_credential_management_api_boundary`

Date: 2026-06-28

## Purpose

This document fixes the project direction before new graph, agent, credential
runtime, or orchestration refactors are added.

The project is an experience-first security research system. It is a research
substrate where human actions, approved tool runs, agent proposals, RAG/RLM
analysis, graph projections, evidence, feedback, and replayable outcomes become
structured memory.

The core loop is:

```text
state
  -> hypothesis
  -> approved action
  -> observation
  -> delta
  -> evidence
  -> structural signal
  -> updated memory
  -> better next choice
```

The system must optimize for accumulated experience, decision quality, replay,
evidence lineage, budget control, and human control.

## System roles

### PostgreSQL

PostgreSQL is canonical memory and the source of truth for operational state.
It owns actions, approvals, budgets, runs, artifacts, outcomes, credentials,
evidence, feedback, proposals, surface snapshots, durable queues, and event
lifecycle state.

Other stores can be rebuilt from PostgreSQL and raw artifact references. They
must not become canonical memory.

### Neo4j and GDS

Neo4j and GDS form a structural signal engine over typed projections. They
produce graph measurements such as connected components, bridges, centrality,
similarity, coverage, drift, neighborhoods, and missing-relation candidates.

Graph math produces structural signals. It does not produce bug verdicts and it
does not execute tools.

### OpenSearch and RAG

OpenSearch is a rebuildable retrieval projection over accumulated evidence and
read models. RAG performs fast retrieval over memory, evidence, summaries,
artifacts, projections, reports, and previous decisions.

RAG returns evidence references and bounded summaries. It does not execute tools
and does not own long-running reasoning state.

### RLM

RLM is a deep recursive analysis path over a selected working context. It may
expand, compress, criticize, and connect evidence from PostgreSQL, RAG results,
structural signals, and task history.

RLM returns analysis summaries, hypothesis proposals, contradictions, and
missing-observation requests. RLM does not execute tools and does not replace
RAG.

### LangGraph agents

LangGraph agents are role/policy workflows over memory and projections. Agents
may read sanitized context, call bounded analysis tasks, compare evidence, and
write typed proposals.

Agents do not receive raw secrets. Agents do not call runners, shell commands,
RabbitMQ, database writes, Neo4j write queries, OpenSearch indexing, or GDS jobs
directly.

### CLI tools and runners

CLI tools are effectors. They run only after a hypothesis or explicitly allowed
discovery step becomes an approved action.

Every tool run must pass through:

```text
ActionService -> policy -> scope -> approval -> budget -> CommandInvocation -> runner
```

The runner boundary executes a validated `CommandInvocation`, writes process
telemetry and artifact metadata, and returns outcomes. It does not choose the
research direction.

### Deterministic domain code

Deterministic code owns exact, cheap, reproducible work:

```text
normalization
fingerprinting
diffing
scope checks
policy checks
budget accounting
credential lease boundaries
artifact lineage
surface snapshots
projection event creation
read-model freshness
replay support
```

It should avoid embedding vulnerability recipes as the primary decision engine.
When exact code can compute a boundary or invariant, use code. When interpretation
or prioritization needs context, use agent/RAG/RLM proposals that still pass
through the control plane.

## Lifecycle contracts

### From signal to execution

Structural signals and retrieved evidence are inputs to hypothesis generation.
They are not findings and not tool runs.

```text
StructuralSignal
  -> HypothesisProposal
  -> ActionProposal
  -> ActionService
  -> policy/scope/approval/budget
  -> CommandInvocation
  -> Outcome
  -> Evidence / SurfaceDelta / ProjectionEvents
```

A hypothesis can be accepted, rejected, merged, or sent back for more evidence.
It must not create live work by itself.

### From outcome to memory

Tool results become useful only after they are normalized, linked, scored, and
made replayable.

```text
runner output
  -> raw artifact metadata
  -> parser / ingestor
  -> canonical facts
  -> surface snapshot or delta
  -> outcome memory
  -> graph/search projection events
  -> feedback and decision-shift traces
```

Raw output volume is telemetry. It is not the main quality score.

## Vulnerability labels

Labels such as `IDOR`, `CSRF`, `JWT-tamper`, `SSRF`, `XSS`, `admin`, or
`auth-boundary` may appear as post-hoc annotations, report labels, operator
search facets, cluster explanations, or evidence summaries.

They must not become the primary action engine. A label alone must not authorize
a runner, bypass policy, select a credential, or promote a finding.

The durable sequence is evidence first, finding later:

```text
observation -> evidence -> reproduction -> human/explicit promotion -> finding
```

## Allowed next-step logic

The system may rank next steps using:

```text
surface deltas
component pressure
graph drift
coverage gaps
similarity to useful historical outcomes
operator feedback
budget state
scope constraints
credential availability metadata
RAG/RLM evidence synthesis
```

The system must keep ranking separate from execution. A ranked candidate becomes
live work only through the action lifecycle.

## Anti-patterns

Avoid these designs:

```text
LLM -> shell
LLM -> RabbitMQ
LLM -> runner
LLM -> raw secret
LLM -> direct database mutation
GDS result -> finding
GDS result -> tool run
scanner output -> LLM verdict -> report
vulnerability enum -> automatic action chain
OpenSearch result -> live command
```

These bypass memory, policy, replay, evidence lineage, or human control.

## Patch rule

Every future patch must answer at least one of these questions:

```text
How does this improve memory?
How does this improve observation quality?
How does this improve delta/replay/evidence lineage?
How does this improve human control?
How does this improve budget/scope/policy safety?
How does this improve structural signal quality?
How does this reduce duplicate or low-utility work?
```

If the answer is missing, the patch should be postponed.
