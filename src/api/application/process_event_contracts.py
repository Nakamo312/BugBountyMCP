"""Application-level process event contract for runner raw streams."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProcessEvent:
    type: Literal[
        "started",
        "stdout",
        "stderr",
        "timeout",
        "terminated",
        "failed",
    ]
    payload: str | None = None
