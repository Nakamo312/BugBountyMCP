"""GAU CLI runner for URL enumeration"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class GAUCliRunner:
    """
    Runner for GetAllURLs (gau) CLI tool.
    Executes gau and yields discovered URLs.
    """

    def __init__(self, gau_path: str, timeout: int = 600):
        self.gau_path = gau_path
        self.timeout = timeout

    async def run(self, domain: str, include_subs: bool = True) -> AsyncIterator[ProcessEvent]:
        """
        Execute gau for the given domain.

        Args:
            domain: Target domain for URL enumeration
            include_subs: Include subdomains in results

        Yields:
            ProcessEvent with type="url" and payload=discovered_url
        """
        command = [
            self.gau_path,
            "--providers", "wayback,commoncrawl,otx,urlscan",
            "--threads", "5",
            "--blacklist", "png,jpg,jpeg,gif,svg,ico,css,woff,woff2,ttf,eot,otf,mp4,mp3,avi,webm,flv,wav,pdf,zip,tar,gz,rar,7z,exe,dll,bin,dmg,iso",
        ]

        if include_subs:
            command.append("--subs")

        command.append(domain)

        logger.info("Starting GAU command: %s", " ".join(command))

        executor = CommandExecutor(command, stdin=None, timeout=self.timeout)

        async for event in executor.run():
            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            url = event.payload.strip()
            if url and self._is_valid_url(url):
                yield ProcessEvent(type="url", payload=url)

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
