from __future__ import annotations

import pytest

from api.application.credential_storage import SecretMaterial
from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.credentials.materialization import (
    CredentialMaterializationError,
    materialize_credential_for_runner,
)


def test_cli_flag_materialization_keeps_secret_out_of_repr_audit_and_log_view() -> None:
    material = SecretMaterial.from_text(kind="api_key", value="real-secret-token")

    plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "cli_flag", "flag": "--api-token"},
    )

    assert plan.apply_to_argv(["tool", "scan"]) == (
        "tool",
        "scan",
        "--api-token",
        "real-secret-token",
    )
    assert plan.redacted_argv(["tool", "scan"]) == (
        "tool",
        "scan",
        "--api-token",
        "<redacted>",
    )
    assert plan.redacted_command_for_log(["tool", "scan"]) == "tool scan --api-token '<redacted>'"
    assert plan.audit_view()["argv_additions"] == [
        {
            "flag": "--api-token",
            "placement": "separate_arg",
            "present": True,
            "redacted": True,
        }
    ]
    assert plan.exposures == ("argv",)
    assert "real-secret-token" not in repr(plan)
    assert "real-secret-token" not in str(plan.audit_view())
    assert "real-secret-token" not in plan.redacted_command_for_log(["tool", "scan"])


def test_cli_flag_equals_materialization_redacts_equals_arg() -> None:
    material = SecretMaterial.from_text(kind="api_key", value="real-secret-token")

    plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "cli_flag_equals", "flag": "--api-token"},
    )

    assert plan.apply_to_argv(["tool"]) == ("tool", "--api-token=real-secret-token")
    assert plan.redacted_argv(["tool"]) == ("tool", "--api-token=<redacted>")
    assert "real-secret-token" not in plan.redacted_command_for_log(["tool"])


def test_env_header_cookie_and_proxy_materialization_are_audit_safe() -> None:
    material = SecretMaterial.from_text(kind="bearer_token", value="real-secret-token")

    env_plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "env", "slot": "TOOL_TOKEN"},
    )
    assert env_plan.apply_to_env({"PATH": "/bin"})["TOOL_TOKEN"] == "real-secret-token"
    assert env_plan.audit_view()["env_additions"] == [
        {"name": "TOOL_TOKEN", "present": True, "redacted": True}
    ]
    invocation = command_invocation(["tool", "scan"], env=env_plan.env_additions)
    assert invocation.process_env({"PATH": "/bin"}) == {
        "PATH": "/bin",
        "TOOL_TOKEN": "real-secret-token",
    }
    assert "real-secret-token" not in str(invocation.env_audit_view)

    header_plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "header", "slot": "Authorization"},
    )
    assert header_plan.header_additions == {"Authorization": "real-secret-token"}
    assert header_plan.audit_view()["header_additions"] == [
        {"name": "Authorization", "present": True, "redacted": True}
    ]

    cookie_plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "cookie", "slot": "session"},
    )
    assert cookie_plan.cookie_additions == {"session": "real-secret-token"}

    proxy_plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "proxy_auth"},
    )
    assert proxy_plan.proxy_auth == "real-secret-token"

    for plan in (env_plan, header_plan, cookie_plan, proxy_plan):
        assert "real-secret-token" not in repr(plan)
        assert "real-secret-token" not in str(plan.audit_view())


def test_file_backed_materialization_uses_temp_file_descriptors_without_audit_leak() -> None:
    material = SecretMaterial.from_text(kind="cookie_jar", value="session=real-secret-token")

    plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": "cookie_jar", "slot": "default"},
    )

    descriptor = plan.temp_files[0]
    assert descriptor.role == "cookie_jar"
    assert descriptor.content == b"session=real-secret-token"
    assert descriptor.file_mode == 0o600
    assert descriptor.audit_view() == {
        "role": "cookie_jar",
        "slot": "default",
        "suffix": ".cookies.txt",
        "file_mode": "0o600",
        "present": True,
        "redacted": True,
    }
    assert "real-secret-token" not in repr(descriptor)
    assert "real-secret-token" not in repr(plan)
    assert "real-secret-token" not in str(plan.audit_view())


@pytest.mark.parametrize(
    ("mode", "slot", "suffix"),
    [
        ("config_file", "api", ".conf"),
        ("browser_context", "user_a", ".browser.json"),
        ("mtls_cert", "client", ".pem"),
    ],
)
def test_supported_file_materialization_modes(mode: str, slot: str, suffix: str) -> None:
    material = SecretMaterial.from_text(kind="custom", value="secret-file-body")

    plan = materialize_credential_for_runner(
        material=material,
        auth_injection={"mode": mode, "slot": slot},
    )

    assert plan.temp_files[0].suffix == suffix
    assert plan.temp_files[0].content == b"secret-file-body"
    assert "secret-file-body" not in str(plan.audit_view())


def test_text_materialization_rejects_binary_or_multiline_secret_values() -> None:
    with pytest.raises(CredentialMaterializationError, match="UTF-8 text secret"):
        materialize_credential_for_runner(
            material=SecretMaterial(kind="api_key", value=b"\xff\xfe"),
            auth_injection={"mode": "env", "slot": "TOOL_TOKEN"},
        )

    with pytest.raises(CredentialMaterializationError, match="single-line"):
        materialize_credential_for_runner(
            material=SecretMaterial.from_text(kind="api_key", value="line1\nline2"),
            auth_injection={"mode": "cli_flag", "flag": "--api-token"},
        )
