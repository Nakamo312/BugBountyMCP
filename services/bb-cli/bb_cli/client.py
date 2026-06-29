from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from .settings import CliSettings


class BbApiError(RuntimeError):
    """User-facing API error raised by the CLI client."""


def runtime_metadata(
    *,
    mode: str,
    deep_confirmed: bool = False,
    surface: str = "cli",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = (mode or "none").strip().lower()
    if normalized not in {"none", "cheap", "normal", "deep"}:
        raise ValueError("agent runtime mode must be one of: none, cheap, normal, deep")
    return {
        **(extra or {}),
        "ui_surface": surface,
        "tool_execution": "forbidden_from_prompt",
        "agent_runtime_mode": normalized,
        "budget_mode": normalized,
        "model_mode": normalized,
        "deep_mode_confirmed": bool(deep_confirmed) if normalized == "deep" else False,
    }


class BbApiClient:
    """Small synchronous HTTP client for the public control-plane API."""

    def __init__(self, settings: CliSettings, *, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.api_token:
            headers["Authorization"] = f"Bearer {settings.api_token}"
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "BbApiClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def workspace(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_limit: int = 20,
        proposal_limit: int = 20,
        action_limit: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "program_id": str(program_id),
            "task_limit": task_limit,
            "proposal_limit": proposal_limit,
            "action_limit": action_limit,
        }
        if campaign_id is not None:
            params["campaign_id"] = str(campaign_id)
        return self._get("/campaign-workspace", params=params)

    def activity(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_id: UUID | None = None,
        after: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"program_id": str(program_id), "limit": limit}
        if campaign_id is not None:
            params["campaign_id"] = str(campaign_id)
        if task_id is not None:
            params["task_id"] = str(task_id)
        if after:
            params["after"] = after
        return self._get("/agent-activity", params=params)

    def program_projection_overview(self, *, program_id: UUID) -> dict[str, Any]:
        return self._get("/program-projection-overview", params={"program_id": str(program_id)})

    def program_projection_plan(self, *, program_id: UUID) -> dict[str, Any]:
        return self._get("/program-projection-overview/plan", params={"program_id": str(program_id)})

    def create_agent_task(
        self,
        *,
        program_id: UUID,
        prompt: str,
        campaign_id: UUID | None = None,
        target_agent: str = "coordinator",
        created_by: str = "cli",
        runtime_mode: str = "none",
        deep_confirmed: bool = False,
        context_refs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "program_id": str(program_id),
            "prompt": prompt,
            "created_by": created_by,
            "target_agent": target_agent,
            "source": "cli",
            "context_refs": context_refs or [],
            "metadata": runtime_metadata(
                mode=runtime_mode,
                deep_confirmed=deep_confirmed,
                surface="cli.agent.ask",
            ),
        }
        if campaign_id is not None:
            payload["campaign_id"] = str(campaign_id)
        return self._post("/agent-tasks", payload)

    def list_agent_tasks(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"program_id": str(program_id), "limit": limit}
        if campaign_id is not None:
            params["campaign_id"] = str(campaign_id)
        if status:
            params["status"] = status
        return self._get("/agent-tasks", params=params)

    def task_detail(self, *, task_id: UUID, message_limit: int = 100) -> dict[str, Any]:
        return self._get(f"/agent-tasks/{task_id}/detail", params={"message_limit": message_limit})

    def reply_agent_task(
        self,
        *,
        task_id: UUID,
        body: str,
        created_by: str = "cli",
        runtime_mode: str = "none",
        deep_confirmed: bool = False,
        context_refs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "body": body,
            "created_by": created_by,
            "source": "cli",
            "context_refs": context_refs or [],
            "metadata": runtime_metadata(
                mode=runtime_mode,
                deep_confirmed=deep_confirmed,
                surface="cli.agent.reply",
            ),
        }
        return self._post(f"/agent-tasks/{task_id}/messages", payload)

    def accept_proposal(
        self,
        *,
        proposal_id: UUID,
        accepted_by: str = "cli",
        reason: str | None = None,
        confidence: float = 0.5,
        proposal_kind: str = "agent",
        capability_id: str | None = None,
        profile_id: str | None = None,
        targets: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_kind = _proposal_kind(proposal_kind)
        payload: dict[str, Any] = {
            "accepted_by": accepted_by,
            "confidence": confidence,
            "targets": targets or [],
            "options": options or {},
            "metadata": {
                "source": "bb-cli",
                "boundary": f"{normalized_kind}_proposal_accept_to_action_service",
            },
        }
        if reason:
            payload["reason"] = reason
        if normalized_kind == "agent":
            if capability_id:
                payload["capability_id"] = capability_id
            if profile_id:
                payload["profile_id"] = profile_id
        elif capability_id or profile_id:
            raise ValueError("--capability-id/--profile-id are only valid for agent proposals")
        return self._post(f"/{_proposal_path(normalized_kind)}/{proposal_id}/accept", payload)

    def review_proposal(
        self,
        *,
        proposal_id: UUID,
        decision: str,
        reviewed_by: str = "cli",
        reason: str | None = None,
        confidence: float = 0.5,
        proposal_kind: str = "agent",
        feedback_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if decision not in {"reject", "suppress"}:
            raise ValueError("decision must be reject or suppress")
        normalized_kind = _proposal_kind(proposal_kind)
        payload: dict[str, Any] = {
            "reviewed_by": reviewed_by,
            "confidence": confidence,
            "metadata": {"source": "bb-cli", "feedback_boundary": f"{normalized_kind}:{decision}"},
        }
        if normalized_kind == "agent":
            payload["feedback_tags"] = feedback_tags or []
        elif feedback_tags:
            payload["metadata"]["feedback_tags"] = feedback_tags
        if reason:
            payload["reason"] = reason
        return self._post(f"/{_proposal_path(normalized_kind)}/{proposal_id}/{decision}", payload)

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.client.get(path, params=params)
            response.raise_for_status()
            return dict(response.json())
        except httpx.HTTPStatusError as exc:
            raise BbApiError(_format_http_error(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise BbApiError(str(exc)) from exc

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.post(path, json=payload)
            response.raise_for_status()
            return dict(response.json())
        except httpx.HTTPStatusError as exc:
            raise BbApiError(_format_http_error(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise BbApiError(str(exc)) from exc


def _proposal_kind(value: str) -> str:
    normalized = (value or "agent").strip().lower().replace("_", "-")
    aliases = {
        "agent": "agent",
        "agent-action": "agent",
        "agent-action-proposal": "agent",
        "experience": "experience",
        "action-experience": "experience",
        "action-experience-proposal": "experience",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError("proposal kind must be agent or experience") from exc


def _proposal_path(kind: str) -> str:
    if kind == "agent":
        return "agent-action-proposals"
    if kind == "experience":
        return "action-experience-proposals"
    raise ValueError("proposal kind must be agent or experience")


def _format_http_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return f"API {response.status_code}: {body}"
