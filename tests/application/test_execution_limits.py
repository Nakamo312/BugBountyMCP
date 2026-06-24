from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.application.execution_limits import (
    ActionInputValidationError,
    ExecutionBudget,
    ExecutionBudgetRequest,
    ToolOptionSpec,
    normalize_options,
    resolve_execution_budget,
)


def test_option_schema_applies_defaults_without_string_coercion() -> None:
    schema = {
        "depth": ToolOptionSpec(
            type="integer",
            default=2,
            minimum=1,
            maximum=5,
        ),
        "headless": ToolOptionSpec(type="boolean", default=False),
    }

    assert normalize_options(schema, {"depth": 4}) == {
        "depth": 4,
        "headless": False,
    }

    with pytest.raises(ActionInputValidationError, match="depth must be integer"):
        normalize_options(schema, {"depth": "4"})


def test_option_schema_rejects_unknown_required_and_enum_values() -> None:
    schema = {
        "mode": ToolOptionSpec(
            type="string",
            required=True,
            enum=("passive", "active"),
        )
    }

    with pytest.raises(ActionInputValidationError, match="Unsupported options"):
        normalize_options(schema, {"unknown": True})
    with pytest.raises(ActionInputValidationError, match="mode is required"):
        normalize_options(schema, {})
    with pytest.raises(ActionInputValidationError, match="mode is not an allowed value"):
        normalize_options(schema, {"mode": "unsafe"})


def test_option_contract_rejects_invalid_ranges_defaults_and_forbidden_keys() -> None:
    with pytest.raises(ValidationError, match="minimum cannot exceed maximum"):
        ToolOptionSpec(type="integer", minimum=5, maximum=2)
    with pytest.raises(ValidationError, match="default must be integer"):
        ToolOptionSpec(type="integer", default="2")

    with pytest.raises(ActionInputValidationError, match="Forbidden command-like options"):
        normalize_options(
            {"shell": ToolOptionSpec(type="string")},
            {"shell": "whoami"},
        )


def test_requested_budget_can_only_reduce_profile_and_system_ceilings() -> None:
    system = ExecutionBudget(
        max_duration_seconds=1800,
        max_targets=1000,
        rate_per_second=1000,
        concurrency=5,
    )
    profile = ExecutionBudget(
        max_duration_seconds=120,
        max_targets=20,
        rate_per_second=10,
        concurrency=2,
    )

    assert resolve_execution_budget(
        system=system,
        profile=profile,
        requested=ExecutionBudgetRequest(max_targets=10),
    ) == ExecutionBudget(
        max_duration_seconds=120,
        max_targets=10,
        rate_per_second=10,
        concurrency=2,
    )

    with pytest.raises(ActionInputValidationError, match="max_targets exceeds"):
        resolve_execution_budget(
            system=system,
            profile=profile,
            requested=ExecutionBudgetRequest(max_targets=21),
        )


def test_profile_budget_cannot_expand_system_ceiling() -> None:
    with pytest.raises(
        ActionInputValidationError,
        match="profile concurrency exceeds system ceiling",
    ):
        resolve_execution_budget(
            system=ExecutionBudget(concurrency=5),
            profile=ExecutionBudget(concurrency=6),
            requested=None,
        )


def test_execution_budget_requires_positive_strict_values() -> None:
    with pytest.raises(ValidationError):
        ExecutionBudget(max_targets=0)
    with pytest.raises(ValidationError):
        ExecutionBudget(concurrency="2")
