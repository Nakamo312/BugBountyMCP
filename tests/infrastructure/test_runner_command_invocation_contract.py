from __future__ import annotations

from pathlib import Path

_RUNNERS_WITH_COMMAND_EXECUTOR = tuple(
    sorted(
        path.name
        for path in Path("src/api/infrastructure/runners").glob("*.py")
        if "CommandExecutor(" in path.read_text() or "executor_cls(invocation)" in path.read_text()
    )
)


def _runner_source(filename: str) -> str:
    return Path("src/api/infrastructure/runners", filename).read_text()


def test_runners_use_command_invocation_contract() -> None:
    assert _RUNNERS_WITH_COMMAND_EXECUTOR

    for filename in _RUNNERS_WITH_COMMAND_EXECUTOR:
        source = _runner_source(filename)

        assert "command_invocation" in source, filename
        assert "CommandExecutor(command," not in source, filename
        assert "CommandExecutor(command=" not in source, filename
        assert "CommandExecutor(\n            command," not in source, filename
        assert "CommandExecutor(\n            command=" not in source, filename
