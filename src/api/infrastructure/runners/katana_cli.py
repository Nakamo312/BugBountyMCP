"""Katana CLI runner for web crawling"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class KatanaCliRunner:
    """
    Runner for Katana CLI tool.
    Executes katana web crawler and yields discovered URLs.
    """

    def __init__(self, katana_path: str, timeout: int = 600):
        self.katana_path = katana_path
        self.timeout = timeout

    async def run(
        self,
        target: str,
        depth: int = 3,
        js_crawl: bool = True,
        headless: bool = False,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Execute katana crawler for the given target.

        Args:
            target: Target URL to crawl
            depth: Maximum crawl depth (default: 3)
            js_crawl: Enable JavaScript endpoint parsing (default: True)
            headless: Enable headless browser crawling (default: False)

        Yields:
            ProcessEvent with type="url" and payload=discovered_url
        """
        command = [
            self.katana_path,
            "-u", target,
            "-d", str(depth),
            "-silent",
            "-jsonl",
            "-c", "10",
            "-p", "5",
            "-rl", "150",
            "-timeout", "10",
            "-ef", "png,jpg,jpeg,gif,svg,ico,css,woff,woff2,ttf,eot,otf,mp4,mp3,avi,webm,flv,wav,pdf,zip,tar,gz,rar,7z,exe,dll,bin,dmg,iso",
        ]

        if js_crawl:
            command.append("-jc")

        if headless:
            command.extend(["-hl", "-nos"])

        logger.info("Starting Katana command: %s", " ".join(command))

        executor = CommandExecutor(command, stdin=None, timeout=self.timeout)

        async for event in executor.run():
            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            line = event.payload.strip()
            if not line:
                continue

            url = self._extract_url(line)
            if url and self._is_valid_url(url):
                yield ProcessEvent(type="url", payload=url)

    def _extract_url(self, line: str) -> str | None:
        """
        Extract URL from katana JSON output.
        Katana outputs JSONL with 'url' field.
        """
        try:
            import json
            data = json.loads(line)
            return data.get("request", {}).get("url") or data.get("url")
        except (json.JSONDecodeError, KeyError):
            if line.startswith("http://") or line.startswith("https://"):
                return line
            return None

    def _is_valid_url(self, value: str) -> bool:
        """
        Validate if string looks like a URL.
        Filters out error messages and non-URL output.
        """
        if not value or len(value) > 2048:
            return False

        if any(keyword in value.lower() for keyword in ["error", "failed", "no such file", "usage:", "flag"]):
            return False

        if not value.startswith(("http://", "https://")):
            return False

        return True
