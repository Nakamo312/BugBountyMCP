"""Subjack CLI runner for subdomain takeover detection"""
import logging
import tempfile
from pathlib import Path
from typing import AsyncIterator, Optional

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class SubjackCliRunner:
    """
    Runner for Subjack CLI tool.
    Detects subdomain takeovers by analyzing CNAME records.
    """

    def __init__(self, subjack_path: str, fingerprints_path: Optional[str] = None, timeout: int = 300):
        self.subjack_path = subjack_path
        self.fingerprints_path = fingerprints_path
        self.timeout = timeout

    async def run(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Execute subjack to detect subdomain takeovers.

        Args:
            targets: Single domain or list of domains to check

        Yields:
            ProcessEvent with type="result" and payload=vulnerability_data
        """
        if isinstance(targets, str):
            targets = [targets]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write('\n'.join(targets))
            tmp.flush()
            wordlist_path = tmp.name

        try:
            command = [
                self.subjack_path,
                "-w", wordlist_path,
                "-t", "100",
                "-timeout", "30",
                "-ssl",
                "-a",
            ]

            if self.fingerprints_path:
                command.extend(["-c", self.fingerprints_path])

            logger.info("Starting Subjack: targets=%d wordlist=%s", len(targets), wordlist_path)

            executor = CommandExecutor(command, timeout=self.timeout)

            result_count = 0
            async for event in executor.run():
                if event.type == "stderr" and event.payload:
                    logger.debug("Subjack stderr: %s", event.payload)

                if event.type != "stdout":
                    continue

                if not event.payload:
                    continue

                line = event.payload.strip()
                if not line:
                    continue

                if line.startswith("[") and "Not Vulnerable" not in line:
                    parts = line.split()
                    if len(parts) < 2:
                        continue

                    try:
                        subdomain = parts[0]
                        service_start = line.find("[")
                        service_end = line.find("]")
                        service = line[service_start+1:service_end] if service_start != -1 and service_end != -1 else "unknown"

                        vulnerable = "Takeover Possible" in line or "possible takeover" in line.lower()

                        if vulnerable:
                            cname = None
                            for part in parts[1:]:
                                if "." in part and not part.startswith("["):
                                    cname = part
                                    break

                            result_count += 1
                            yield ProcessEvent(
                                type="result",
                                payload={
                                    "subdomain": subdomain,
                                    "service": service,
                                    "vulnerable": True,
                                    "cname": cname
                                }
                            )
                    except (IndexError, ValueError) as e:
                        logger.debug("Failed to parse Subjack line: %r - %s", line, e)

            logger.info("Subjack completed: vulnerabilities=%d", result_count)
        finally:
            Path(wordlist_path).unlink(missing_ok=True)
