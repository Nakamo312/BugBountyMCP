# Graph Math Role

Status: baseline for typed projection and GDS work after patch 0040

Date: 2026-06-28

## Purpose

Graph math is the structural signal layer of the experience-first research
system. Its job is to measure structure over typed projections and return
signals that can help humans, agents, RAG/RLM tasks, and planners choose what to
inspect next.

Graph math must not act as a bug oracle. It does not know that a vulnerability
exists. It reports pressure, drift, coverage gaps, unusual neighborhoods,
bridges, similarity, centrality, and missing-relation candidates.

## Source of truth and projection boundary

PostgreSQL owns canonical facts, events, artifacts, surface snapshots, outcomes,
evidence, and feedback. Neo4j receives rebuildable projections from durable
PostgreSQL state and artifact-derived facts.

A graph projection can be deleted and rebuilt. A projection result can be
persisted as a read model or structural signal only with lineage back to:

```text
program_id
snapshot_id or projection_version
source facts / node refs / edge refs
evidence refs where available
generator name and version
```

## Typed projections

A named projection is a mathematical space with explicit node types, edge types,
required facts, intended algorithms, and forbidden interpretations.

The planned inventory starts with:

```text
G_asset
G_http
G_identity
G_finding
G_temporal
G_bipartite_endpoint_param
G_bipartite_host_tech
G_bipartite_endpoint_object
```

Each projection must define:

```text
name
node types
edge types
required facts
purpose
allowed algorithms
output signal types
lineage requirements
sensitivity rules
```

A projection must not be a loose dump of all available nodes. Mixed graphs can
exist for evidence paths, but analytical GDS projections should state their
mathematical space.

## Current graph-math contours

The project already has two useful contours.

The experience contour:

```text
ActionOutcome <-> OutcomeFeature
  -> node similarity
  -> learned capability/profile ranking
```

The Surface Map contour:

```text
SurfaceNode --SURFACE_EDGE-- SurfaceNode
  -> connected components
  -> degree
  -> betweenness
  -> node similarity
  -> component pressure
  -> drift
  -> bridges
  -> outliers
  -> coverage
  -> advisory candidates
```

These contours should be extended through typed contracts rather than rebuilt as
ad-hoc queries.

## Structural signals

Graph math output should become a structural signal when it can influence a
choice and can be traced.

A structural signal is conceptually:

```text
StructuralSignal
  signal_type
  projection_name
  node_refs
  edge_refs
  score
  evidence_refs
  snapshot_id or projection_version
  generated_by
  generated_at
```

A signal is not a finding. It can support a hypothesis proposal, a coverage plan,
a RAG query, an RLM deep-analysis task, or an operator dashboard.

## Allowed algorithm families

Use algorithms that describe structure without encoding vulnerability recipes:

```text
connected components
weakly connected components
centrality
degree distributions
betweenness / bridge pressure
community detection where useful
node similarity
neighborhood overlap
link prediction baselines
bipartite similarity
coverage scoring
temporal drift
spectral summaries where justified
```

Every algorithm must state its projection, input facts, output signal, and known
failure modes.

## Forbidden shortcut

Do not encode logic like:

```text
param name contains id -> IDOR action
admin path -> admin scan
jwt observed -> JWT tamper run
csrf token missing -> finding
```

Those may become analyst annotations or hypothesis text after evidence review.
They must not be graph-math action engines.

## Relationship to RAG, RLM, and LangGraph

Graph math selects and ranks structural context. RAG retrieves evidence around
that context. RLM performs deeper analysis over a bounded working set. LangGraph
coordinates role workflows and writes proposals.

The execution boundary remains outside graph math:

```text
graph signal
  -> analysis task
  -> hypothesis proposal
  -> action proposal
  -> ActionService
```

Graph math never calls a runner.

## Projection quality rules

A new projection or algorithm should be accepted only when it improves at least
one of these:

```text
coverage visibility
drift visibility
component understanding
missing-relation discovery
historical-experience reuse
hypothesis selection
budget reduction
replay and evidence lineage
```

If a projection mainly adds labels, taxonomy, or dashboard decoration, postpone
it.
