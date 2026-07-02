import logging
import sys

import pytest

from api.infrastructure.commands.command_boundary import (
    CommandInvocation,
    command_invocation,
    format_command_for_log,
    redact_command_argv,
    summarize_env_for_log,
    summarize_stdin_for_log,
    validate_command_argv,
    validate_command_env,
    validate_command_credential_refs,
    validate_command_stdin,
    validate_command_timeout,
)
from api.infrastructure.commands.command_executor import CommandExecutor


def test_command_boundary_redacts_sensitive_option_values() -> None:
    command = [
        "curl",
        "-H",
        "Authorization: Bearer secret-token",
        "--cookie=session=abc",
        "--token",
        "secret",
        "https://example.test",
    ]

    assert redact_command_argv(command) == [
        "curl",
        "-H",
        "<redacted>",
        "--cookie=<redacted>",
        "--token",
        "<redacted>",
        "https://example.test",
    ]
    rendered = format_command_for_log(command)
    assert "secret-token" not in rendered
    assert "session=abc" not in rendered
    assert " secret" not in rendered


@pytest.mark.parametrize(
    "command",
    [
        [],
        [""],
        ["httpx", "bad\x00arg"],
        ["httpx", object()],
    ],
)
def test_command_boundary_rejects_invalid_argv(command) -> None:
    with pytest.raises(ValueError):
        validate_command_argv(command)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), 86_401])
def test_command_boundary_rejects_invalid_timeouts(timeout) -> None:
    with pytest.raises(ValueError):
        validate_command_timeout(timeout)


def test_stdin_log_summary_never_returns_payload() -> None:
    stdin = "https://one.example\nhttps://two.example"

    assert summarize_stdin_for_log(stdin) == "present(chars=39 lines=2)"
    assert "one.example" not in summarize_stdin_for_log(stdin)


def test_command_executor_validates_command_and_timeout_at_boundary() -> None:
    with pytest.raises(ValueError):
        CommandExecutor([], timeout=1)
    with pytest.raises(ValueError):
        CommandExecutor(["echo"], timeout=0)


def test_command_invocation_is_validated_execution_contract() -> None:
    invocation = command_invocation(
        ["httpx", "--token", "secret-token"],
        stdin="https://one.example",
        timeout=17,
        env={"TOOL_TOKEN": "secret-token"},
        credential_refs=("lease:program:abc",),
    )

    assert invocation.argv == ("httpx", "--token", "secret-token")
    assert invocation.stdin == "https://one.example"
    assert invocation.timeout == 17
    assert dict(invocation.env) == {"TOOL_TOKEN": "secret-token"}
    assert invocation.credential_refs == ("lease:program:abc",)
    assert "secret-token" not in invocation.command_for_log
    assert "secret-token" not in str(invocation.env_audit_view)
    assert invocation.stdin_summary == "present(chars=19)"



def test_command_invocation_validates_and_redacts_env_overlay() -> None:
    invocation = command_invocation(
        ["tool"],
        env={"TOOL_TOKEN": "secret-token", "SAFE_MODE": "1"},
    )

    assert dict(invocation.env) == {"TOOL_TOKEN": "secret-token", "SAFE_MODE": "1"}
    assert invocation.env_audit_view == [
        {"name": "SAFE_MODE", "present": True, "redacted": True},
        {"name": "TOOL_TOKEN", "present": True, "redacted": True},
    ]
    assert summarize_env_for_log(invocation.env) == "present(names=SAFE_MODE,TOOL_TOKEN)"
    assert invocation.process_env({"PATH": "/bin"}) == {
        "PATH": "/bin",
        "SAFE_MODE": "1",
        "TOOL_TOKEN": "secret-token",
    }


@pytest.mark.parametrize(
    "env",
    [
        {"": "x"},
        {"BAD-NAME": "x"},
        {"BAD": object()},
        {"BAD": "x\x00y"},
        [("KEY", "value")],
    ],
)
def test_command_env_boundary_rejects_invalid_values(env) -> None:
    with pytest.raises(ValueError):
        validate_command_env(env)

def test_command_invocation_rejects_secret_like_invalid_boundary_values() -> None:
    with pytest.raises(ValueError):
        command_invocation(["httpx"], stdin=object())
    with pytest.raises(ValueError):
        command_invocation(["httpx"], stdin="bad\x00input")
    with pytest.raises(ValueError):
        command_invocation(["httpx"], credential_refs=("",))
    with pytest.raises(ValueError):
        validate_command_credential_refs("lease")
    with pytest.raises(ValueError):
        validate_command_stdin(object())


def test_command_executor_accepts_command_invocation_without_legacy_overrides() -> None:
    invocation = CommandInvocation(["echo", "ok"], stdin="hello", timeout=3)

    executor = CommandExecutor(invocation)

    assert executor.invocation is invocation
    assert executor.command == ["echo", "ok"]
    assert executor.stdin == "hello"
    assert executor.timeout == 3
    assert executor.env == {}


def test_command_executor_rejects_command_invocation_with_legacy_overrides() -> None:
    invocation = CommandInvocation(["echo", "ok"], timeout=3)

    with pytest.raises(ValueError):
        CommandExecutor(invocation, stdin="override")
    with pytest.raises(ValueError):
        CommandExecutor(invocation, timeout=4)
    with pytest.raises(ValueError):
        CommandExecutor(invocation, env={"TOOL_TOKEN": "override"})


@pytest.mark.asyncio
async def test_command_executor_passes_env_overlay_to_process() -> None:
    executor = CommandExecutor(
        command_invocation(
            [sys.executable, "-c", "import os; print(os.environ.get('BB_TEST_MARKER'))"],
            env={"BB_TEST_MARKER": "visible"},
            timeout=5,
        )
    )

    events = [event async for event in executor.run()]

    assert any(event.type == "stdout" and event.payload == "visible" for event in events)
    assert any(event.type == "terminated" for event in events)


@pytest.mark.asyncio
async def test_command_executor_logs_env_names_without_values(caplog) -> None:
    caplog.set_level(logging.INFO, logger="api.infrastructure.commands.command_executor")
    secret_value = "super-secret-env-token"
    executor = CommandExecutor(
        command_invocation(
            [sys.executable, "-c", "print('ok')"],
            env={"TOOL_TOKEN": secret_value},
            timeout=5,
        )
    )

    events = [event async for event in executor.run()]

    assert any(event.type == "terminated" for event in events)
    log_text = caplog.text
    assert "TOOL_TOKEN" in log_text
    assert secret_value not in log_text

@pytest.mark.asyncio
async def test_command_executor_drains_stdout_after_fast_process_exit() -> None:
    executor = CommandExecutor(
        command_invocation(
            [
                sys.executable,
                "-c",
                "for i in range(200): print(f'line-{i}')",
            ],
            timeout=5,
        )
    )

    events = [event async for event in executor.run()]
    stdout = [event.payload for event in events if event.type == "stdout"]

    assert len(stdout) == 200
    assert stdout[0] == "line-0"
    assert stdout[-1] == "line-199"
    assert any(event.type == "terminated" and event.payload == "0" for event in events)


@pytest.mark.asyncio
async def test_command_executor_reports_nonzero_returncode_in_terminated_event() -> None:
    executor = CommandExecutor(
        command_invocation([sys.executable, "-c", "import sys; sys.exit(7)"], timeout=5)
    )

    events = [event async for event in executor.run()]

    assert any(event.type == "terminated" and event.payload == "7" for event in events)


@pytest.mark.asyncio
async def test_command_executor_does_not_wait_for_grandchild_holding_stdout_pipe() -> None:
    executor = CommandExecutor(
        command_invocation(
            ["/bin/sh", "-c", "sleep 30 & echo parent-finished"],
            timeout=2,
        )
    )

    events = [event async for event in executor.run()]

    assert any(event.type == "stdout" and event.payload == "parent-finished" for event in events)
    assert any(event.type == "terminated" and event.payload == "0" for event in events)
    assert not any(event.type == "timeout" for event in events)
