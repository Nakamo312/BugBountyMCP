"""Legacy FFUF scan service facade."""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from uuid import UUID

from api.application.dto.scan_dto import FFUFScanOutputDTO


class FFUFScanService:
    STATIC_EXTENSIONS = {
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".mp3",
        ".pdf",
        ".ico",
        ".webp",
        ".otf",
    }

    def __init__(self, runner, bus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: list[str]) -> FFUFScanOutputDTO:
        return FFUFScanOutputDTO(
            status="started",
            message=f"FFUF scan started for {len(targets)} targets",
            scanner="ffuf",
            targets_count=len(targets),
        )

    def _parse_ffuf_jsonline(self, line: str) -> dict | None:
        if not line or not line.strip():
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        if "url" not in data or "status" not in data:
            return None

        return {
            "url": data.get("url"),
            "status": data.get("status"),
            "length": data.get("length", 0),
            "words": data.get("words", 0),
            "lines": data.get("lines", 0),
            "content_type": data.get("content-type", ""),
            "redirect_location": data.get("redirectlocation", ""),
        }

    def _filter_static_files(self, results: list[dict]) -> list[dict]:
        filtered = []
        for result in results:
            url = result.get("url")
            if not url:
                continue

            path = urlsplit(url).path.lower()
            if any(path.endswith(extension) for extension in self.STATIC_EXTENSIONS):
                continue

            filtered.append(result)
        return filtered
