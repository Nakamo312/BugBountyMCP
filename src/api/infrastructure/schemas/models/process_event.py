from dataclasses import dataclass
from typing import Literal, Optional

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
    payload: Optional[str] = None
