"""Naabu Service for port scanning"""

import logging
from uuid import UUID

from api.application.dto.scan_dto import NaabuScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.naabu_cli import NaabuCliRunner
from api.application.services.batch_processor import NaabuBatchProcessor

logger = logging.getLogger(__name__)


class NaabuScanService:
    """
    Event-driven service for Naabu port scanning.

    Supports:
    - Active port scanning (SYN/CONNECT)
    - Passive port enumeration (Shodan InternetDB)
    - Nmap service detection integration
    - Top ports and custom port ranges
    """

    def __init__(
        self,
        runner: NaabuCliRunner,
        processor: NaabuBatchProcessor,
        bus: EventBus
    ):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(
        self,
        program_id: UUID,
        hosts: list[str],
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 1000,
        scan_type: str = "c",
        exclude_cdn: bool = True
    ) -> NaabuScanOutputDTO:
        """
        Execute active port scan on hosts and publish results to EventBus.

        Args:
            program_id: Program UUID
            hosts: List of hosts/IPs to scan
            ports: Port specification (e.g., "80,443,8080-8090") or None for top-ports
            top_ports: Top ports preset - "100", "1000", "full" (default: "1000")
            rate: Packets per second (default: 1000)
            scan_type: Scan type - "s" (SYN) or "c" (CONNECT) (default: "c")
            exclude_cdn: Skip full port scans for CDN/WAF, only scan 80,443 (default: True)

        Returns:
            NaabuScanOutputDTO with scan results summary
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

        batches = []
        async for batch in self.processor.process(results):
            batches.append(batch)

        total_results = sum(len(batch) for batch in batches)

        if batches:
            for batch in batches:
                await self.bus.publish(
                    EventType.NAABU_RESULTS_BATCH,
                    {
                        "program_id": str(program_id),
                        "results": batch,
                        "scan_mode": "active",
                        "scan_type": scan_type,
                        "ports": ports or f"top-{top_ports}"
                    }
                )

        logger.info(
            f"Naabu active scan completed: program={program_id} "
            f"hosts={len(hosts)} open_ports={total_results} batches={len(batches)}"
        )

        return NaabuScanOutputDTO(
            status="completed",
            message=f"Active scan completed: {len(hosts)} hosts, {total_results} open ports discovered",
            scanner="naabu",
            targets_count=len(hosts),
            scan_mode="active"
        )

    async def execute_passive(
        self,
        program_id: UUID,
        hosts: list[str]
    ) -> NaabuScanOutputDTO:
        """
        Execute passive port enumeration using Shodan InternetDB API.

        Args:
            program_id: Program UUID
            hosts: List of hosts/IPs to query

        Returns:
            NaabuScanOutputDTO with scan results summary
        """
        logger.info(
            f"Starting naabu passive scan: program={program_id} hosts={len(hosts)}"
        )

        results = []
        async for event in self.runner.passive_scan(hosts=hosts):
            results.append(event)

        batches = []
        async for batch in self.processor.process(results):
            batches.append(batch)

        total_results = sum(len(batch) for batch in batches)

        if batches:
            for batch in batches:
                await self.bus.publish(
                    EventType.NAABU_RESULTS_BATCH,
                    {
                        "program_id": str(program_id),
                        "results": batch,
                        "scan_mode": "passive"
                    }
                )

        logger.info(
            f"Naabu passive scan completed: program={program_id} "
            f"hosts={len(hosts)} ports={total_results} batches={len(batches)}"
        )

        return NaabuScanOutputDTO(
            status="completed",
            message=f"Passive scan completed: {len(hosts)} hosts, {total_results} ports discovered from Shodan",
            scanner="naabu",
            targets_count=len(hosts),
            scan_mode="passive"
        )

    async def execute_with_nmap(
        self,
        program_id: UUID,
        hosts: list[str],
        nmap_cli: str = "nmap -sV",
        top_ports: str = "1000",
        rate: int = 1000
    ) -> NaabuScanOutputDTO:
        """
        Execute port scan with nmap service detection.

        Args:
            program_id: Program UUID
            hosts: List of hosts/IPs to scan
            nmap_cli: Nmap command for service detection (default: "nmap -sV")
            top_ports: Top ports preset (default: "1000")
            rate: Packets per second (default: 1000)

        Returns:
            NaabuScanOutputDTO with scan results summary
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

        batches = []
        async for batch in self.processor.process(results):
            batches.append(batch)

        total_results = sum(len(batch) for batch in batches)

        if batches:
            for batch in batches:
                await self.bus.publish(
                    EventType.NAABU_RESULTS_BATCH,
                    {
                        "program_id": str(program_id),
                        "results": batch,
                        "scan_mode": "nmap",
                        "nmap_cli": nmap_cli,
                        "ports": f"top-{top_ports}"
                    }
                )

        logger.info(
            f"Naabu+nmap scan completed: program={program_id} "
            f"hosts={len(hosts)} results={total_results} batches={len(batches)}"
        )

        return NaabuScanOutputDTO(
            status="completed",
            message=f"Nmap scan completed: {len(hosts)} hosts, {total_results} results with service detection",
            scanner="naabu",
            targets_count=len(hosts),
            scan_mode="nmap"
        )
