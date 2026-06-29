from __future__ import annotations

import json
from uuid import uuid4

import httpx


def json_request(request: httpx.Request) -> dict:
    return json.loads(request.content.decode())


class RecordingTransport(httpx.MockTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/agent-tasks") and request.method == "POST":
            payload = json_request(request)
            return httpx.Response(
                202,
                json={
                    "task": {
                        "task_id": str(uuid4()),
                        "program_id": payload["program_id"],
                        "campaign_id": payload.get("campaign_id"),
                        "correlation_id": str(uuid4()),
                        "status": "queued",
                        "target_agent": payload["target_agent"],
                        "title": "Agent task",
                        "prompt_excerpt": payload["prompt"],
                        "prompt_hash": "hash",
                        "created_by": payload["created_by"],
                        "source": payload["source"],
                        "context_refs": [],
                        "metadata": payload["metadata"],
                        "created_at": "2026-06-27T00:00:00Z",
                        "updated_at": "2026-06-27T00:00:00Z",
                        "inbox_message_id": str(uuid4()),
                    },
                    "first_message": {
                        "message_id": str(uuid4()),
                        "task_id": str(uuid4()),
                        "program_id": payload["program_id"],
                        "campaign_id": payload.get("campaign_id"),
                        "correlation_id": str(uuid4()),
                        "role": "user",
                        "message_kind": "note",
                        "agent_key": None,
                        "body": payload["prompt"],
                        "body_hash": "hash",
                        "artifact_refs": [],
                        "fact_refs": [],
                        "graph_refs": [],
                        "action_refs": [],
                        "proposal_refs": [],
                        "decision_refs": [],
                        "metadata": payload["metadata"],
                        "created_at": "2026-06-27T00:00:00Z",
                    },
                },
            )
        if request.url.path.endswith("/campaign-workspace"):
            return httpx.Response(
                200,
                json={
                    "program_id": str(uuid4()),
                    "campaign_id": None,
                    "generated_at": "2026-06-27T00:00:00Z",
                    "tasks": [],
                    "pending_agent_proposals": [],
                    "pending_experience_proposals": [],
                    "recent_decisions": [],
                    "action_queue": [],
                    "counts": {"tasks": 0},
                    "agent_runtime_usage": {"selected_modes": {"none": 1}},
                    "boundaries": {},
                },
            )
        if request.url.path.endswith("/program-projection-overview/plan"):
            program_id = str(request.url.params.get("program_id"))
            return httpx.Response(
                200,
                json={
                    "program_id": program_id,
                    "ui_data_fresh": False,
                    "step_count": 1,
                    "next_step": {
                        "step_id": "process-search-projection-events",
                        "priority": 70,
                        "severity": "warning",
                        "area": "search_projection",
                        "title": "Process pending search projection events",
                        "reason": "Incremental OpenSearch projection events are pending.",
                        "commands": ["search_indexer process-events --program-id " + program_id],
                        "blocks_ui_freshness": True,
                    },
                    "steps": [
                        {
                            "step_id": "process-search-projection-events",
                            "priority": 70,
                            "severity": "warning",
                            "area": "search_projection",
                            "title": "Process pending search projection events",
                            "reason": "Incremental OpenSearch projection events are pending.",
                            "commands": ["search_indexer process-events --program-id " + program_id],
                            "blocks_ui_freshness": True,
                        }
                    ],
                    "boundary": {"gds_execution": "forbidden", "plan_semantics": "ordered_commands_only_not_execution"},
                },
            )
        if request.url.path.endswith("/program-projection-overview"):
            program_id = str(request.url.params.get("program_id"))
            return httpx.Response(
                200,
                json={
                    "program_id": program_id,
                    "latest_surface_snapshot": {
                        "snapshot_id": str(uuid4()),
                        "snapshot_fingerprint": "snap-fp",
                        "algorithm": "surface-map",
                        "algorithm_version": "v1",
                        "node_count": 10,
                        "edge_count": 12,
                        "delta_count": 2,
                        "created_at": "2026-06-27T00:00:00Z",
                    },
                    "latest_surface_analysis": {
                        "analysis_run_id": str(uuid4()),
                        "snapshot_id": str(uuid4()),
                        "previous_snapshot_id": None,
                        "report_fingerprint": "report-fp",
                        "algorithm": "surface-components",
                        "algorithm_version": "v1",
                        "item_count": 3,
                        "created_at": "2026-06-27T00:00:01Z",
                    },
                    "surface_analysis_fresh": True,
                    "search_index_fresh": False,
                    "ui_data_fresh": False,
                    "graph_projection_events": {"pending": 0, "locked": 0, "processed": 8, "failed": 0, "dead": 0},
                    "graph_fact_batches": {"pending": 0, "locked": 0, "processed": 0, "applied": 8, "failed": 0, "dead": 0},
                    "surface_analysis_events": {"pending": 0, "locked": 0, "processed": 1, "failed": 0, "dead": 0},
                    "search_projection_events": {"pending": 2, "locked": 0, "processed": 0, "failed": 0, "dead": 0},
                    "search_index": {
                        "surface_components_indexed": False,
                        "surface_deltas_indexed": False,
                        "latest_surface_components_event_status": "pending",
                        "latest_surface_deltas_event_status": "pending",
                        "latest_surface_components_event_at": "2026-06-27T00:00:02Z",
                        "latest_surface_deltas_event_at": "2026-06-27T00:00:02Z",
                    },
                    "experience_proposals": {"pending": 4, "accepted": 1, "rejected": 2, "suppressed": 1},
                    "suggested_commands": ["search_indexer process-events"],
                    "boundary": {"gds_execution": "forbidden", "opensearch_reindex": "forbidden"},
                },
            )
        return httpx.Response(404, json={"detail": "not found"})
