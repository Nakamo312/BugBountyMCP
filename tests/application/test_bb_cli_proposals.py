from __future__ import annotations

from uuid import uuid4

import httpx
from bb_cli.client import BbApiClient
from bb_cli.settings import CliSettings

from tests.application.bb_cli_support import json_request


def test_client_accepts_experience_proposal_through_experience_endpoint() -> None:
    class AcceptTransport(httpx.MockTransport):
        def __init__(self):
            self.requests: list[httpx.Request] = []
            super().__init__(self._handle)

        def _handle(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(
                202,
                json={
                    "proposal": {"proposal_id": request.url.path.split("/")[-2], "status": "accepted"},
                    "action_submission": {"status": "queued", "action": {"action_id": str(uuid4())}},
                    "boundary": {"submitted_through_action_service": True},
                },
            )

    transport = AcceptTransport()
    client = BbApiClient(CliSettings(api_url="http://testserver", program_id=uuid4()), transport=transport)
    proposal_id = uuid4()

    client.accept_proposal(
        proposal_id=proposal_id,
        proposal_kind="experience",
        targets=["https://example.test"],
        reason="use component candidate",
    )

    request = transport.requests[-1]
    payload = json_request(request)
    assert request.url.path == f"/api/v1/action-experience-proposals/{proposal_id}/accept"
    assert payload["targets"] == ["https://example.test"]
    assert payload["metadata"]["boundary"] == "experience_proposal_accept_to_action_service"
    assert "capability_id" not in payload


def test_client_rejects_experience_proposal_through_experience_endpoint() -> None:
    class ReviewTransport(httpx.MockTransport):
        def __init__(self):
            self.requests: list[httpx.Request] = []
            super().__init__(self._handle)

        def _handle(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(
                200,
                json={
                    "proposal": {"proposal_id": request.url.path.split("/")[-2], "status": "rejected"},
                    "boundary": {"action_submitted": False},
                },
            )

    transport = ReviewTransport()
    client = BbApiClient(CliSettings(api_url="http://testserver", program_id=uuid4()), transport=transport)
    proposal_id = uuid4()

    client.review_proposal(
        proposal_id=proposal_id,
        proposal_kind="experience",
        decision="reject",
        reason="not useful",
        feedback_tags=["noisy"],
    )

    request = transport.requests[-1]
    payload = json_request(request)
    assert request.url.path == f"/api/v1/action-experience-proposals/{proposal_id}/reject"
    assert payload["metadata"]["feedback_boundary"] == "experience:reject"
    assert payload["metadata"]["feedback_tags"] == ["noisy"]
    assert "feedback_tags" not in payload


def test_cli_parser_supports_experience_proposal_kind() -> None:
    from bb_cli.__main__ import build_parser

    proposal_id = str(uuid4())
    args = build_parser().parse_args(
        [
            "--program-id",
            str(uuid4()),
            "proposal",
            "accept",
            proposal_id,
            "--kind",
            "experience",
            "--target",
            "https://example.test",
        ]
    )

    assert args.command == "proposal"
    assert args.proposal_command == "accept"
    assert args.kind == "experience"
    assert args.targets == ["https://example.test"]


def test_render_proposal_list_includes_experience_proposals() -> None:
    from bb_cli.render import render_proposals_from_workspace

    proposal_id = str(uuid4())
    text = render_proposals_from_workspace(
        {
            "pending_agent_proposals": [],
            "pending_experience_proposals": [
                {
                    "proposal_id": proposal_id,
                    "status": "pending",
                    "rank": 1,
                    "capability_id": "linkfinder",
                    "profile_id": "default",
                    "utility_score": 0.81,
                    "sample_count": 7,
                    "avg_similarity": 0.64,
                    "explanation": {"source": "neo4j-jaccard-surface-component"},
                }
            ],
        }
    )

    assert "Action experience proposals" in text
    assert "linkfinder/default" in text
    assert f"bb proposal accept {proposal_id} --kind experience --target <target>" in text
    assert f"bb proposal suppress {proposal_id} --kind experience" in text
