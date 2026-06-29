# Hypothesis From Structural Signal Contract

Status: contract-only shape inventory.

This document describes the boundary that turns structural graph signals into
hypothesis proposals. It does not create a database table, write events, create
findings, create action proposals, approve tools, or execute commands.

Machine-checkable source:

```text
services/graph-projector/graph_projector/hypothesis_from_signal_contract.py
```

The module validates this shape at import time. A broken mapping between
structural signal types and hypothesis proposal types should fail early.

## Role

A structural signal can support a hypothesis proposal. The proposal is a review
object for human, RAG, RLM, or evidence critic workflows. It is not an action and
not a finding.

Boundary:

```text
StructuralSignal -> HypothesisProposal -> ActionProposal -> ActionService approval -> Tool run -> Outcome
```

The contract in this patch covers only the first transition:

```text
StructuralSignal -> HypothesisProposal
```

Hard boundary:

```text
hypothesis proposal != finding
hypothesis proposal != action proposal
hypothesis proposal != approval request
hypothesis proposal != command invocation
hypothesis proposal != exploit recipe
```

## Event shape

The v1 event type is:

```text
hypothesis_proposal_created
```

The source event type is:

```text
structural_signal_generated
```

Required event fields:

```text
proposal_id
proposal_type
hypothesis_type
program_id
status
source_signal_ids
source_signal_types
projection_refs
evidence_refs
missing_observations
confidence
priority_score
safety_level
score_version
source_event_ids
generated_by
generated_at
```

Reference fields are references only:

```text
source_signal_ids
projection_refs
evidence_refs
source_event_ids
```

They must not embed raw HTTP payloads, raw parameter values, secrets, cookies,
Authorization headers, command argv, or artifact bodies.

## Status and scoring

Allowed v1 statuses:

```text
proposed
needs_review
```

`confidence` is bounded to `0.0..1.0` at the contract level.
`priority_score` is bounded to `0..100` at the contract level.

These numbers rank review work. They are not severity, proof, impact, or exploit
probability.

## Proposal type mapping

Every structural signal type from `structural_signal_contract.py` must map to
exactly one hypothesis proposal type:

```text
HttpEndpointNeighborhoodSignal -> http_endpoint_neighborhood_review
HttpCoverageGapSignal -> http_coverage_gap_review
HttpDriftSignal -> http_drift_review
HttpMissingRelationCandidateSignal -> http_missing_relation_review
EndpointParamSimilaritySignal -> endpoint_param_similarity_review
ParamCentralitySignal -> param_centrality_review
MissingEndpointParamCandidateSignal -> missing_endpoint_param_candidate_review
```

The mapping keeps the source signal id, projection refs, and evidence refs. It
also records missing observations for later RAG/RLM or evidence critic tasks.

## Allowed next steps

Allowed next steps are review and analysis tasks:

```text
human_review
rag_context_task
rlm_deep_analysis_task
evidence_critic_task
action_proposal_draft
```

`action_proposal_draft` is still only a draft. It does not execute a tool and it
must later pass the normal `ActionService -> policy -> scope -> approval -> budget`
path.

Forbidden next steps:

```text
tool_run
command_invocation
action_execution
auto_approve
```

## Forbidden event fields

The proposal event must not include fields that skip into another lifecycle:

```text
finding_id
finding_status
action_id
action_proposal_id
approval_request_id
command_invocation_id
command_argv
credential_secret_version_id
credential_lease_id
tool_name
tool_args
runner_id
```

## Forbidden payload fields

The proposal must not carry raw sensitive payloads:

```text
raw_headers
raw_request_body
raw_response_body
raw_body
body_preview
raw_url
full_url
url_sample
query
fragment
example_value
raw_value
secret_value
query_value
authorization
cookies
token
secret
password
api_key
session_cookie
raw_evidence
raw_payload
exploit_steps
reproduction_steps
command_template
curl_command
```

## Current relationship to existing hypothesis code

The existing `src/api/application/hypotheses.py` workflow stores sanitized
`HypothesisCandidate` values from result-set context. This contract does not
replace that workflow. It defines the future structural-signal-derived proposal
boundary so a later implementation can map proposals into the same safe storage
model without giving graph signals the power to create findings or run tools.
