from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.notify_channels import listen_statement, validate_postgres_notify_channel


def test_graph_projector_notify_channel_validator_contract() -> None:
    assert validate_postgres_notify_channel("graph_fact_batches_changed") == "graph_fact_batches_changed"
    assert listen_statement("graph_projection_events_changed") == "LISTEN graph_projection_events_changed;"

    with pytest.raises(ValueError):
        validate_postgres_notify_channel("bad;NOTIFY x")
    with pytest.raises(ValueError):
        listen_statement("1bad")
