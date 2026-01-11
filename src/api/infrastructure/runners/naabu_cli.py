"""Naabu CLI Runner"""

import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent

logger = logging.getLogger(__name__)


class NaabuCliRunner:
    """
    Runs naabu CLI tool for port scanning.

    Naabu features:
    - Fast SYN/CONNECT probe scanning
    - Top ports scanning
    - JSON output support
    - Rate limiting
    - IPv4/IPv6 support
    """

    def __init__(self, naabu_path: str, timeout: int = 600):
        self.naabu_path = naabu_path
        self.timeout = timeout

    async def run(self, hosts: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Default run method for pipeline compatibility.

        Args:
            hosts: Single host/IP or list of hosts/IPs to scan

        Yields:
            ProcessEvent with type="result" and payload=dict with naabu JSON output
        """
        async for event in self.scan(hosts):
            yield event

    async def scan(
        self,
        hosts: list[str] | str,
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 1000,
        scan_type: str = "c",
        exclude_cdn: bool = True
    ) -> AsyncIterator[ProcessEvent]:
        """
        Port scan hosts with naabu.

        Args:
            hosts: Single host/IP or list of hosts/IPs to scan
            ports: Port specification (e.g., "80,443,8080-8090") or None for top-ports
            top_ports: Top ports preset - "100", "1000", "full" (default: "1000")
            rate: Packets per second (default: 1000)
            scan_type: Scan type - "s" (SYN) or "c" (CONNECT) (default: "c")
            exclude_cdn: Skip full port scans for CDN/WAF, only scan 80,443 (default: True)

        Yields:
            ProcessEvent with type="result" and payload=dict with naabu JSON output

        Naabu JSON output format:
        {
            "host": "8.8.8.8",
            "ip": "8.8.8.8",
            "port": 53,
            "protocol": "tcp"
        }
        """
        if isinstance(hosts, str):
            hosts = [hosts]

        command = [
            self.naabu_path,
            "-json",
            "-silent",
            "-s", scan_type,
            "-rate", str(rate),
        ]

        if ports:
            command.extend(["-p", ports])
        else:
            command.extend(["-top-ports", top_ports])

        if exclude_cdn:
            command.append("-exclude-cdn")

        stdin = "\n".join(hosts)

        logger.info(
            f"Starting naabu scan: hosts={len(hosts)} ports={ports or f'top-{top_ports}'} "
            f"rate={rate} type={scan_type} exclude_cdn={exclude_cdn}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"naabu stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug(f"Non-JSON stdout line skipped: {event.payload!r}")
                continue

        logger.info(f"naabu scan completed: open_ports={result_count}")

    async def scan_with_nmap(
        self,
        hosts: list[str] | str,
        nmap_cli: str = "nmap -sV",
        top_ports: str = "1000",
        rate: int = 1000
    ) -> AsyncIterator[ProcessEvent]:
        """
        Port scan with naabu and invoke nmap for service detection.

        Args:
            hosts: Single host/IP or list of hosts/IPs
            nmap_cli: Nmap command for service detection (default: "nmap -sV")
            top_ports: Top ports preset (default: "1000")
            rate: Packets per second (default: 1000)

        Yields:
            ProcessEvent with naabu results (nmap results not captured separately)
        """
        if isinstance(hosts, str):
            hosts = [hosts]

        command = [
            self.naabu_path,
            "-json",
            "-silent",
            "-top-ports", top_ports,
            "-rate", str(rate),
            "-nmap-cli", nmap_cli,
        ]

        stdin = "\n".join(hosts)

        logger.info(
            f"Starting naabu scan with nmap: hosts={len(hosts)} "
            f"top_ports={top_ports} nmap='{nmap_cli}'"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"naabu stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug(f"Non-JSON stdout line skipped: {event.payload!r}")
                continue

        logger.info(f"naabu+nmap scan completed: results={result_count}")

    async def passive_scan(
        self,
        hosts: list[str] | str
    ) -> AsyncIterator[ProcessEvent]:
        """
        Passive port enumeration using Shodan InternetDB API.

        Args:
            hosts: Single host/IP or list of hosts/IPs

        Yields:
            ProcessEvent with passive port discovery results
        """
        if isinstance(hosts, str):
            hosts = [hosts]

        command = [
            self.naabu_path,
            "-json",
            "-silent",
            "-passive",
        ]

        stdin = "\n".join(hosts)

        logger.info(f"Starting naabu passive scan: hosts={len(hosts)}")

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"naabu stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug(f"Non-JSON stdout line skipped: {event.payload!r}")
                continue

        logger.info(f"naabu passive scan completed: results={result_count}")
