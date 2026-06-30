from __future__ import annotations

from api.application.pipeline.invocation import option_map


def test_option_map_ignores_payload_fields_without_explicit_options() -> None:
    event = {
        "event": "host_discovered",
        "payload": {
            "url": "https://example.test",
            "runner_invocation_context": {"node_id": "httpx"},
            "new_control_field": "must-not-become-runner-option",
        },
    }

    assert option_map(event) == {}
