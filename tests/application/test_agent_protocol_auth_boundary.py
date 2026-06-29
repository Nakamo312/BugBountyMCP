from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.presentation.rest.security import require_agent_protocol_internal_access


class _Request:
    def __init__(self, settings: object) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(settings=settings))


def _settings(**overrides: object) -> object:
    values = {
        "AGENT_PROTOCOL_INTERNAL_TOKEN": "expected-token",
        "AGENT_PROTOCOL_ALLOWED_ACTORS": "agent-worker,operator,admin",
        "AGENT_PROTOCOL_ALLOW_UNAUTHENTICATED_INTERNAL": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_agent_protocol_access_requires_allowed_actor_and_matching_token() -> None:
    principal = require_agent_protocol_internal_access(
        _Request(_settings()),
        x_agent_actor="agent-worker",
        x_agent_internal_token="expected-token",
    )

    assert principal.actor == "agent-worker"


@pytest.mark.parametrize(
    ("actor", "token", "detail"),
    (
        (None, "expected-token", "agent protocol access denied"),
        ("browser", "expected-token", "agent protocol access denied"),
        ("agent-worker", None, "agent protocol access denied"),
        ("agent-worker", "wrong-token", "agent protocol access denied"),
    ),
)
def test_agent_protocol_access_rejects_missing_actor_or_invalid_token(
    actor: str | None,
    token: str | None,
    detail: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_agent_protocol_internal_access(
            _Request(_settings()),
            x_agent_actor=actor,
            x_agent_internal_token=token,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == detail


def test_agent_protocol_access_fails_closed_when_token_is_not_configured() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_agent_protocol_internal_access(
            _Request(_settings(AGENT_PROTOCOL_INTERNAL_TOKEN=None)),
            x_agent_actor="agent-worker",
            x_agent_internal_token="anything",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "agent protocol internal token is not configured"


def test_agent_protocol_dev_bypass_still_requires_allowed_actor() -> None:
    settings = _settings(
        AGENT_PROTOCOL_INTERNAL_TOKEN=None,
        AGENT_PROTOCOL_ALLOW_UNAUTHENTICATED_INTERNAL=True,
    )

    principal = require_agent_protocol_internal_access(
        _Request(settings),
        x_agent_actor="operator",
        x_agent_internal_token=None,
    )

    assert principal.actor == "operator"

    with pytest.raises(HTTPException):
        require_agent_protocol_internal_access(
            _Request(settings),
            x_agent_actor="browser",
            x_agent_internal_token=None,
        )
