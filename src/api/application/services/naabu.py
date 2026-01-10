"""Naabu Service for port scanning"""

import logging
from typing import AsyncIterator, Dict, Any
from uuid import UUID

from api.infrastructure.runners.naabu_cli import NaabuCliRunner
from api.application.services.batch_processor import NaabuBatchProcessor

logger = logging.getLogger(__name__)


class NaabuScanService:
    """
    Service for Naabu port scanning.
    Streams batched results for pipeline node processing.

    Supports:
    - Active port scanning (SYN/CONNECT)
    - Passive port enumeration (Shodan InternetDB)
    - Nmap service detection integration
    - Top ports and custom port ranges
    """

    def __init__(
        self,
        runner: NaabuCliRunner,
        processor: NaabuBatchProcessor
    ):
        self.runner = runner
        self.processor = processor

    async def execute(
        self,
        program_id: UUID,
        hosts: list[str],
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 150,
        scan_type: str = "c",
        exclude_cdn: bool = True
    ) -> AsyncIterator[list[Dict[str, Any]]]:
        """
        Execute active port scan and yield batched results.

        Args:
            program_id: Program UUID
            hosts: List of hosts/IPs to scan
            ports: Port specification (e.g., "80,443,8080-8090") or None for top-ports
            top_ports: Top ports preset - "100", "1000", "full" (default: "1000")
            rate: Packets per second (default: 150)
            scan_type: Scan type - "s" (SYN) or "c" (CONNECT) (default: "c")
            exclude_cdn: Skip full port scans for CDN/WAF, only scan 80,443 (default: True)

        Yields:
            Batches of Naabu scan results with metadata
        """
        logger.info(
            f"Starting naabu active scan: program={program_id} hosts={len(hosts)} "
            f"ports={ports or f'top-{top_ports}'} rate={rate} type={scan_type} "
            f"exclude_cdn={exclude_cdn}"
        )

        results = []
        async for event in self.runner.scan(
            hosts=hosts,
            ports=ports,
            top_ports=top_ports,
            rate=rate,
            scan_type=scan_type,
            exclude_cdn=exclude_cdn
        ):
            results.append(event)

        batches_yielded = 0
        total_results = 0

        async for batch in self.processor.process(results):
            if batch:
                batches_yielded += 1
                total_results += len(batch)
                logger.debug(f"Naabu active batch ready: program={program_id} count={len(batch)}")

                batch_with_meta = {
                    "results": batch,
                    "scan_mode": "active",
                    "scan_type": scan_type,
                    "ports": ports or f"top-{top_ports}"
                }
                yield batch_with_meta

        logger.info(
            f"Naabu active scan completed: program={program_id} "
            f"hosts={len(hosts)} open_ports={total_results} batches={batches_yielded}"
        )

    async def execute_passive(
        self,
        program_id: UUID,
        hosts: list[str]
    ) -> AsyncIterator[list[Dict[str, Any]]]:
        """
        Execute passive port enumeration and yield batched results.

        Args:
            program_id: Program UUID
            hosts: List of hosts/IPs to query

        Yields:
            Batches of Naabu passive results with metadata
        """
        logger.info(
            f"Starting naabu passive scan: program={program_id} hosts={len(hosts)}"
        )

        results = []
        async for event in self.runner.passive_scan(hosts=hosts):
            results.append(event)

        batches_yielded = 0
        total_results = 0

        async for batch in self.processor.process(results):
            if batch:
                batches_yielded += 1
                total_results += len(batch)
                logger.debug(f"Naabu passive batch ready: program={program_id} count={len(batch)}")

                batch_with_meta = {
                    "results": batch,
                    "scan_mode": "passive"
                }
                yield batch_with_meta

        logger.info(
            f"Naabu passive scan completed: program={program_id} "
            f"hosts={len(hosts)} ports={total_results} batches={batches_yielded}"
        )

    async def execute_with_nmap(
        self,
        program_id: UUID,
        hosts: list[str],
        nmap_cli: str = "nmap -sV",
        top_ports: str = "1000",
        rate: int = 1000
    ) -> AsyncIterator[list[Dict[str, Any]]]:
        """
        Execute port scan with nmap service detection and yield batched results.

        Args:
            program_id: Program UUID
            hosts: List of hosts/IPs to scan
            nmap_cli: Nmap command for service detection (default: "nmap -sV")
            top_ports: Top ports preset (default: "1000")
            rate: Packets per second (default: 1000)

        Yields:
            Batches of Naabu+Nmap results with metadata
        """
        logger.info(
            f"Starting naabu scan with nmap: program={program_id} hosts={len(hosts)} "
            f"top_ports={top_ports} nmap='{nmap_cli}'"
        )

        results = []
        async for event in self.runner.scan_with_nmap(
            hosts=hosts,
            nmap_cli=nmap_cli,
            top_ports=top_ports,
            rate=rate
        ):
            results.append(event)

        batches_yielded = 0
        total_results = 0

        async for batch in self.processor.process(results):
            if batch:
                batches_yielded += 1
                total_results += len(batch)
                logger.debug(f"Naabu+nmap batch ready: program={program_id} count={len(batch)}")

                batch_with_meta = {
                    "results": batch,
                    "scan_mode": "nmap",
                    "nmap_cli": nmap_cli,
                    "ports": f"top-{top_ports}"
                }
                yield batch_with_meta

        logger.info(
            f"Naabu+nmap scan completed: program={program_id} "
            f"hosts={len(hosts)} results={total_results} batches={batches_yielded}"
        )
