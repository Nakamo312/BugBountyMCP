from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from api.application.capability_catalog import build_tool_catalog_snapshot
from api.application.pipeline.yaml_config import (
    DEFAULT_PIPELINE_CONFIG_PATH,
    PipelineConfig,
    load_pipeline_config,
)


def _typed_manifest() -> dict:
    return {
        "workers": {"demo": {"type": "scan"}},
        "capabilities": {
            "demo": {
                "label": "Demo",
                "request_event": "demo_requested",
                "queue": "analysis",
                "default_profile": "safe",
                "mode": "manual",
                "profiles": {
                    "safe": {
                        "label": "Safe",
                        "safety_level": "safe_active",
                        "options": {
                            "timeout": {
                                "type": "integer",
                                "default": 30,
                                "minimum": 1,
                                "maximum": 60,
                            }
                        },
                        "budgets": {
                            "max_duration_seconds": 60,
                            "max_targets": 5,
                            "rate_per_second": 10,
                            "concurrency": 2,
                        },
                    }
                },
            }
        },
    }


def test_profile_supports_typed_options_and_hard_budgets() -> None:
    config = PipelineConfig.model_validate(_typed_manifest())

    profile = config.capabilities["demo"].profiles["safe"]

    assert profile.allowed_option_names == ("timeout",)
    assert profile.options["timeout"].default == 30
    assert profile.budgets.max_targets == 5


def test_profile_rejects_conflicting_legacy_and_typed_option_names() -> None:
    payload = _typed_manifest()
    payload["capabilities"]["demo"]["profiles"]["safe"]["allowed_options"] = [
        "depth"
    ]

    with pytest.raises(
        ValidationError,
        match="allowed_options and options must declare the same keys",
    ):
        PipelineConfig.model_validate(payload)


def test_catalog_hash_changes_when_profile_budget_changes() -> None:
    config = load_pipeline_config(DEFAULT_PIPELINE_CONFIG_PATH)
    original = build_tool_catalog_snapshot(config)
    payload = deepcopy(config.model_dump(mode="json"))
    capability_id = next(iter(payload["capabilities"]))
    profile_id = next(iter(payload["capabilities"][capability_id]["profiles"]))
    payload["capabilities"][capability_id]["profiles"][profile_id]["budgets"] = {
        "max_targets": 99
    }

    changed = build_tool_catalog_snapshot(PipelineConfig.model_validate(payload))

    assert changed.catalog_hash != original.catalog_hash


def test_catalog_entry_exposes_profile_schema_and_budget() -> None:
    snapshot = build_tool_catalog_snapshot(
        PipelineConfig.model_validate(_typed_manifest())
    )

    entry = snapshot.entries[0]

    assert entry.allowed_options == ("timeout",)
    assert entry.option_schema["timeout"].maximum == 60
    assert entry.execution_budget.concurrency == 2

