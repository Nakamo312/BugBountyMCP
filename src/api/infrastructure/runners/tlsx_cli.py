"""TLSx CLI Runner"""

import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser

logger = logging.getLogger(__name__)


class TLSxCliRunner:
    """
    Runs tlsx CLI tool for TLS/SSL certificate enumeration.

    Supports:
    - Default certificate scanning (extract SAN/CN from default certs)
    - SNI brute-force (probe IPs with known domain names)
    - Certificate chain analysis
    """

    def __init__(self, tlsx_path: str, timeout: int = 300):
        self.tlsx_path = tlsx_path
        self.timeout = timeout

    async def run(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Default run method for pipeline compatibility.

        Args:
            targets: Single target or list of targets (IPs, domains, IP:PORT)

        Yields:
            ProcessEvent with type="result" and payload=cert_data
        """
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event

    async def run_raw(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        async for event in self.scan_default_certs_raw(targets):
            yield event

    async def scan_default_certs_raw(
        self,
        targets: list[str] | str,
        ports: list[int] | None = None
    ) -> AsyncIterator[ProcessEvent]:
        """
        Scan default TLS certificates on targets.

        Args:
            targets: Single target or list of targets (IPs, domains, IP:PORT)
            ports: List of ports to scan (default: 443, 8443)

        Yields:
            Raw ProcessEvent objects from CommandExecutor.

        Output format:
        {
            "timestamp": "2026-01-10T12:00:00Z",
            "host": "91.218.135.4",
            "port": "443",
            "probe_status": true,
            "tls_version": "tls13",
            "cipher": "TLS_AES_128_GCM_SHA256",
            "subject_cn": "t-access.ru",
            "subject_an": ["t-access.ru", "www.t-access.ru"],
            "issuer_cn": "R3",
            "issuer_org": ["Let's Encrypt"]
        }
        """
        if isinstance(targets, str):
            targets = [targets]

        if ports is None:
            ports = [443, 8443]

        command = [
            self.tlsx_path,
            "-json",
            "-silent",
            "-san",
            "-cn"
        ]

        for port in ports:
            command.extend(["-port", str(port)])

        stdin = "\n".join(targets)

        logger.info(
            f"Starting tlsx default cert scan: targets={len(targets)} ports={ports}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"tlsx stderr: {event.payload}")
            yield event

        logger.info("tlsx default cert scan completed")

    async def scan_default_certs(
        self,
        targets: list[str] | str,
        ports: list[int] | None = None
    ) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.scan_default_certs_raw(targets, ports=ports)):
            yield event

    async def scan_sni_brute_raw(
        self,
        ips: list[str] | str,
        domains: list[str],
        ports: list[int] | None = None
    ) -> AsyncIterator[ProcessEvent]:
        """
        SNI brute-force: probe IPs with known domain names.

        Args:
            ips: Single IP or list of IPs to probe
            domains: List of domain names to use as SNI values
            ports: List of ports to scan (default: 443, 8443)

        Yields:
            Raw ProcessEvent objects from CommandExecutor.

        This discovers virtual hosts on shared IPs by testing known
        domain names against IP addresses.
        """
        if isinstance(ips, str):
            ips = [ips]

        if ports is None:
            ports = [443, 8443]

        command = [
            self.tlsx_path,
            "-json",
            "-silent",
            "-san",
            "-cn"
        ]

        for port in ports:
            command.extend(["-port", str(port)])

        targets = []
        for ip in ips:
            for domain in domains:
                for port in ports:
                    targets.append(f"{ip}:{port}@{domain}")

        stdin = "\n".join(targets)

        logger.info(
            f"Starting tlsx SNI brute: ips={len(ips)} domains={len(domains)} "
            f"ports={ports} total_probes={len(targets)}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"tlsx stderr: {event.payload}")
            yield event

        logger.info("tlsx SNI brute completed")

    async def scan_sni_brute(
        self,
        ips: list[str] | str,
        domains: list[str],
        ports: list[int] | None = None
    ) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(
            self.scan_sni_brute_raw(ips, domains=domains, ports=ports)
        ):
            yield event

    async def scan_with_options_raw(
        self,
        targets: list[str] | str,
        ports: list[int] | None = None,
        include_cipher: bool = False,
        include_hash: bool = False,
        include_jarm: bool = False
    ) -> AsyncIterator[ProcessEvent]:
        """
        Advanced TLS scan with additional options.

        Args:
            targets: Single target or list of targets
            ports: List of ports to scan
            include_cipher: Include cipher suite info
            include_hash: Include certificate hash
            include_jarm: Include JARM fingerprint

        Yields:
            Raw ProcessEvent objects from CommandExecutor.
        """
        if isinstance(targets, str):
            targets = [targets]

        if ports is None:
            ports = [443]

        command = [
            self.tlsx_path,
            "-json",
            "-silent",
            "-san",
            "-cn"
        ]

        for port in ports:
            command.extend(["-port", str(port)])

        if include_cipher:
            command.append("-cipher")

        if include_hash:
            command.append("-hash", "sha256")

        if include_jarm:
            command.append("-jarm")

        stdin = "\n".join(targets)

        logger.info(
            f"Starting tlsx advanced scan: targets={len(targets)} "
            f"cipher={include_cipher} hash={include_hash} jarm={include_jarm}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"tlsx stderr: {event.payload}")
            yield event

        logger.info("tlsx advanced scan completed")

    async def scan_with_options(
        self,
        targets: list[str] | str,
        ports: list[int] | None = None,
        include_cipher: bool = False,
        include_hash: bool = False,
        include_jarm: bool = False
    ) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(
            self.scan_with_options_raw(
                targets,
                ports=ports,
                include_cipher=include_cipher,
                include_hash=include_hash,
                include_jarm=include_jarm,
            )
        ):
            yield event
