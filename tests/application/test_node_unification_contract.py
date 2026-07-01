"""RED contract tests for removing tool-specific pipeline nodes.

These tests describe the target state: one generic ScanNode handles all tool
execution shapes through declarative runtime metadata. They are intentionally
RED until the node-unification refactor lands.
"""
from __future__ import annotations

from pathlib import Path
from typing import get_args

import yaml

from api.application.pipeline.yaml_config import NodeType, PipelineNodeSpec

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = ROOT / "src" / "api" / "application" / "pipeline"
PIPELINE_YAML = PIPELINE_DIR / "pipeline.yaml"
FACTORY = PIPELINE_DIR / "factory.py"
CUSTOM_NODE_FILES = (
    PIPELINE_DIR / "nodes" / "ffuf_node.py",
    PIPELINE_DIR / "nodes" / "amass_node.py",
    PIPELINE_DIR / "nodes" / "hakip2host_node.py",
)


def test_node_type_contract_has_single_execution_node() -> None:
    """The declarative pipeline should expose one execution node kind."""
    assert get_args(NodeType) == ("scan",)


def test_runtime_contract_describes_non_batch_execution_shapes() -> None:
    """Per-target execution must be data, not a separate node class."""
    spec = PipelineNodeSpec.model_validate(
        {
            "type": "scan",
            "inputs": ["ffuf_scan_requested"],
            "outputs": {},
            "runner": "FFUFCliRunner",
            "parser": "FFUFParser",
            "processor": "FFUFProcessor",
            "ingestor": "EndpointIngestor",
            "runtime": {
                "mode": "per_target",
                "target_shape": "scalar",
                "artifact": "per_target",
                "concurrency": 5,
            },
        }
    )

    assert spec.type == "scan"
    assert spec.runtime is not None
    assert spec.runtime.mode == "per_target"
    assert spec.runtime.target_shape == "scalar"
    assert spec.runtime.artifact == "per_target"
    assert spec.runtime.concurrency == 5


def test_pipeline_yaml_uses_only_generic_scan_nodes() -> None:
    """pipeline.yaml must not introduce tool-specific node kinds."""
    raw = yaml.safe_load(PIPELINE_YAML.read_text(encoding="utf-8"))
    workers = raw.get("workers") or raw.get("nodes") or {}
    node_types = {spec.get("type") for spec in workers.values() if isinstance(spec, dict)}

    assert node_types <= {"scan"}


def test_custom_node_modules_are_removed() -> None:
    """Tool-specific orchestration classes should disappear after migration."""
    existing = [path.relative_to(ROOT).as_posix() for path in CUSTOM_NODE_FILES if path.exists()]

    assert existing == []


def test_factory_does_not_branch_on_tool_specific_node_types() -> None:
    """The factory should construct ScanNode from declarative runtime metadata."""
    source = FACTORY.read_text(encoding="utf-8")

    forbidden_fragments = (
        "nodes.ffuf_node",
        "nodes.amass_node",
        "nodes.hakip2host_node",
        'spec.type == "ffuf"',
        'spec.type == "amass"',
        'spec.type == "hakip2host"',
        '"ffuf", "amass", "hakip2host"',
    )
    found = [fragment for fragment in forbidden_fragments if fragment in source]

    assert found == []
