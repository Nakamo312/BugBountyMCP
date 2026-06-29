from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status


@dataclass(frozen=True)
class AgentProtocolPrincipal:
    actor: str


def _allowed_agent_protocol_actors(raw: str | None) -> set[str]:
    actors = {actor.strip() for actor in (raw or "").split(",") if actor.strip()}
    return actors or {"agent-worker", "operator", "admin"}


def require_agent_protocol_internal_access(
    request: Request,
    x_agent_actor: Annotated[str | None, Header(alias="X-Agent-Actor")] = None,
    x_agent_internal_token: Annotated[
        str | None, Header(alias="X-Agent-Internal-Token")
    ] = None,
) -> AgentProtocolPrincipal:
    """Guard agent coordination endpoints behind an explicit internal boundary.

    Agent protocol routes coordinate durable inbox/result-set/workflow state.
    They are not public product APIs and must not be callable by browser UI,
    LangGraph tools, or anonymous clients.
    """

    settings = getattr(request.app.state, "settings", None)
    actor = (x_agent_actor or "").strip()
    allowed_actors = _allowed_agent_protocol_actors(
        getattr(settings, "AGENT_PROTOCOL_ALLOWED_ACTORS", None)
    )
    if not actor or actor not in allowed_actors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="agent protocol access denied",
        )

    configured_token = getattr(settings, "AGENT_PROTOCOL_INTERNAL_TOKEN", None)
    allow_unauthenticated_dev = bool(
        getattr(settings, "AGENT_PROTOCOL_ALLOW_UNAUTHENTICATED_INTERNAL", False)
    )
    if not configured_token:
        if allow_unauthenticated_dev:
            return AgentProtocolPrincipal(actor=actor)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="agent protocol internal token is not configured",
        )

    if not hmac.compare_digest(str(x_agent_internal_token or ""), str(configured_token)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="agent protocol access denied",
        )

    return AgentProtocolPrincipal(actor=actor)
