from __future__ import annotations

import json
from pathlib import Path


def test_action_experience_proposals_flat_module_stays_removed() -> None:
    assert not Path("services/graph-projector/graph_projector/action_experience_proposals.py").exists()


def test_action_experience_proposals_package_modules_are_separated() -> None:
    package = Path("services/graph-projector/graph_projector/action_experience/proposals")
    expected = {
        "__init__.py",
        "constants.py",
        "protocols.py",
        "store.py",
        "worker.py",
    }
    assert expected <= {path.name for path in package.iterdir()}

    store_source = (package / "store.py").read_text(encoding="utf-8")
    worker_source = (package / "worker.py").read_text(encoding="utf-8")

    assert "class ActionExperienceProposalStore" in store_source
    assert "class ActionExperienceProposalWorker" not in store_source
    assert "Neo4jDriver" not in store_source

    assert "class ActionExperienceProposalWorker" in worker_source
    assert "class ActionExperienceProposalStore" not in worker_source
    assert "from .store import ActionExperienceProposalStore" in worker_source


def test_action_experience_proposals_allowlist_does_not_preserve_flat_file() -> None:
    allowlist = json.loads(Path("governance/review_gates_allowlist.json").read_text(encoding="utf-8"))
    assert "services/graph-projector/graph_projector/action_experience_proposals.py" not in allowlist["long_files"]
