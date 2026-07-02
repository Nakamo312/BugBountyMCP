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


def test_profile_budget_larger_than_system_is_clamped_to_system_ceiling() -> None:
    assert resolve_execution_budget(
        system=ExecutionBudget(concurrency=5),
        profile=ExecutionBudget(concurrency=6),
        requested=None,
    ) == ExecutionBudget(concurrency=5)


def test_execution_budget_requires_positive_strict_values() -> None:
    with pytest.raises(ValidationError):
        ExecutionBudget(max_targets=0)
    with pytest.raises(ValidationError):
        ExecutionBudget(concurrency="2")


def test_credential_ref_and_auth_injection_options_are_typed_metadata() -> None:
    schema = {
        "credential_ref": ToolOptionSpec(type="credential_ref", required=True),
        "auth_injection": ToolOptionSpec(type="auth_injection", required=True),
    }

    assert normalize_options(
        schema,
        {
            "credential_ref": "credref:program/acme/session/low_priv",
            "auth_injection": {
                "mode": "header",
                "header_name": "Authorization",
            },
        },
    ) == {
        "credential_ref": "credref:program/acme/session/low_priv",
        "auth_injection": {"mode": "header", "slot": "Authorization"},
    }

    with pytest.raises(ActionInputValidationError, match="credential_ref"):
        normalize_options(schema, {"credential_ref": "Bearer real-token", "auth_injection": {"mode": "header", "slot": "Authorization"}})
    with pytest.raises(ActionInputValidationError, match="requires slot"):
        normalize_options(
            schema,
            {
                "credential_ref": "credref:program/acme/session/low_priv",
                "auth_injection": {"mode": "header"},
            },
        )


def test_action_options_reject_raw_credential_material() -> None:
    with pytest.raises(ActionInputValidationError, match="raw credential option"):
        normalize_options(
            {"authorization": ToolOptionSpec(type="string")},
            {"authorization": "Bearer secret-token"},
        )

    with pytest.raises(ActionInputValidationError, match="raw credential material"):
        normalize_options(
            {"note": ToolOptionSpec(type="string")},
            {"note": "Authorization: Bearer secret-token"},
        )

    with pytest.raises(ActionInputValidationError, match="raw credential material"):
        normalize_options(
            {"auth_injection": ToolOptionSpec(type="auth_injection")},
            {"auth_injection": {"mode": "header", "slot": "Authorization", "value": "secret"}},
        )


def test_auth_injection_supports_runner_specific_cli_flag_metadata() -> None:
    schema = {
        "credential_ref": ToolOptionSpec(type="credential_ref", required=True),
        "auth_injection": ToolOptionSpec(
            type="auth_injection",
            required=True,
            allowed_modes=("cli_flag", "cli_flag_equals", "env"),
            allowed_cli_flags=("--api-token", "-k"),
            allow_argv_exposure=True,
        ),
    }

    assert normalize_options(
        schema,
        {
            "credential_ref": "credref:program/acme/identity/user_a",
            "auth_injection": {
                "mode": "cli_flag",
                "flag": "--api-token",
            },
        },
    ) == {
        "credential_ref": "credref:program/acme/identity/user_a",
        "auth_injection": {
            "mode": "cli_flag",
            "flag": "--api-token",
            "placement": "separate_arg",
        },
    }

    assert normalize_options(
        schema,
        {
            "credential_ref": "credref:program/acme/identity/user_a",
            "auth_injection": {
                "mode": "cli_flag_equals",
                "flag": "--api-token",
            },
        },
    )


def test_cli_auth_injection_requires_profile_opt_in_and_allowed_flag() -> None:
    with pytest.raises(ValueError, match="allowed_cli_flags require allow_argv_exposure"):
        ToolOptionSpec(type="auth_injection", allowed_cli_flags=("--token",))

    schema_without_argv_opt_in = {
        "auth_injection": ToolOptionSpec(type="auth_injection"),
    }
    with pytest.raises(ActionInputValidationError, match="argv-exposed"):
        normalize_options(
            schema_without_argv_opt_in,
            {"auth_injection": {"mode": "cli_flag", "flag": "--token"}},
        )

    schema = {
        "auth_injection": ToolOptionSpec(
            type="auth_injection",
            allowed_modes=("cli_flag",),
            allowed_cli_flags=("--api-token",),
            allow_argv_exposure=True,
        ),
    }
    with pytest.raises(ActionInputValidationError, match="unsupported CLI auth flag"):
        normalize_options(
            schema,
            {"auth_injection": {"mode": "cli_flag", "flag": "--random-token"}},
        )
    with pytest.raises(ActionInputValidationError, match="unsupported auth injection mode"):
        normalize_options(
            schema,
            {"auth_injection": {"mode": "env", "env_name": "TOOL_TOKEN"}},
        )


def test_auth_injection_supports_cookie_and_non_argv_modes_without_secret_values() -> None:
    schema = {
        "auth_injection": ToolOptionSpec(
            type="auth_injection",
            allowed_modes=("cookie", "cookie_jar", "browser_context", "mtls_cert", "proxy_auth"),
        ),
    }

    assert normalize_options(
        schema,
        {"auth_injection": {"mode": "cookie", "cookie_name": "sessionid"}},
    ) == {"auth_injection": {"mode": "cookie", "slot": "sessionid"}}
    assert normalize_options(
        schema,
        {"auth_injection": {"mode": "cookie_jar", "slot": "user_a"}},
    ) == {"auth_injection": {"mode": "cookie_jar", "slot": "user_a"}}

    with pytest.raises(ActionInputValidationError, match="raw credential material"):
        normalize_options(
            schema,
            {"auth_injection": {"mode": "cookie", "cookie_name": "sessionid", "value": "abc"}},
        )
