from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from api.application.process_event_contracts import ProcessEvent


@dataclass(frozen=True)
class ToolRunnerRef:
    """Application-level reference to a named tool runner.

    Concrete infrastructure may back this with CLI tools, remote runners,
    replay runners, or another execution backend. Application scan code must
    depend on this reference instead of infrastructure runner classes.
    """

    tool_name: str
    default_options: Mapping[str, Any] = field(default_factory=dict)
    label: str | None = None

    def __str__(self) -> str:
        return self.label or f"tool:{self.tool_name}"


class ToolRunnerPort(Protocol):
    """Application-facing contract for named tool runners.

    Pipeline execution consumes raw events through ``run_raw`` before parser
    application. Services such as MapCIDR consume parsed events through ``run``.
    A runner returned by ``ToolRunnerFactoryPort`` must support both methods;
    otherwise callers would need to know concrete runner families again.
    """

    async def run_raw(self, targets: Any, **options: Any) -> AsyncIterator[ProcessEvent]:
        """Run the tool and yield raw process events."""
        ...

    async def run(self, targets: Any, **options: Any) -> AsyncIterator[ProcessEvent]:
        """Run the tool and yield parsed process events."""
        ...


class ToolRunnerFactoryPort(Protocol):
    """Application-facing factory for named tool runners."""

    def create(self, tool_name: str, **options: Any) -> ToolRunnerPort:
        """Create a runner for a named tool."""
        ...
