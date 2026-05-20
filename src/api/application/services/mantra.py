"""Legacy Mantra scan service facade."""
from __future__ import annotations

import re
from uuid import UUID

from api.application.dto.scan_dto import MantraScanOutputDTO


class MantraScanService:
    def __init__(self, runner, bus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: list[str]) -> MantraScanOutputDTO:
        return MantraScanOutputDTO(
            status="started",
            message=f"Mantra scan started for {len(targets)} JS files",
            scanner="mantra",
            targets_count=len(targets),
        )

    def _parse_mantra_output(self, line: str) -> dict[str, str] | None:
        clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        match = re.match(r"^\[\+\]\s+(https?://[^\s]+)\s+\[(.+)\]$", clean_line)
        if not match:
            return None
        return {"url": match.group(1), "secret": match.group(2)}
