# api/application/services/httpx.py

import asyncio
import json
import logging
from typing import AsyncIterator, Dict, Any, List
from uuid import UUID

from api.application.dto.scan_dto import (
    HTTPXScanInputDTO,
    HTTPXScanOutputDTO,
)
from api.config import Settings
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork

logger = logging.getLogger(__name__)


class HTTPXScanService:
    """
    Application service for ingesting httpx scan results.

    Responsibilities:
    - execute httpx
    - orchestrate ingestion pipeline
    - no dedup logic
    - no SQL / ORM logic
    """

    def __init__(self, uow_factory, settings: Settings):
        self.uow_factory = uow_factory
        self.settings = settings

    # =========================
    # Public API
    # =========================

    async def execute(
        self,
        input_dto: HTTPXScanInputDTO
    ) -> HTTPXScanOutputDTO:

        logger.info(
            "Starting HTTPX scan: program=%s targets=%s",
            input_dto.program_id,
            input_dto.targets,
        )

        async with self.uow_factory() as uow:
            hosts_seen: set[str] = set()
            endpoints_count = 0

            async for data in self._execute_httpx_scan(
                input_dto.targets,
                input_dto.timeout,
            ):
                try:
                    host_name = data.get("host") or data.get("input")
                    if not host_name:
                        continue

                    await self._ingest_result(
                        uow=uow,
                        program_id=input_dto.program_id,
                        data=data,
                    )

                    hosts_seen.add(host_name)
                    endpoints_count += 1

                except Exception as exc:
                    logger.exception(
                        "Failed to ingest httpx result: %s",
                        exc,
                    )

            await uow.commit()

        logger.info(
            "HTTPX scan finished: hosts=%d endpoints=%d",
            len(hosts_seen),
            endpoints_count,
        )

        return HTTPXScanOutputDTO(
            scanner="httpx",
            hosts=len(hosts_seen),
            endpoints=endpoints_count,
            services=endpoints_count,
        )

    # =========================
    # Ingestion pipeline
    # =========================

    async def _ingest_result(
        self,
        uow: HTTPXUnitOfWork,
        program_id: UUID,
        data: Dict[str, Any],
    ) -> None:
        """
        Ingest single httpx JSON line into domain model.
        """

        # -------- Host --------
        host_name = data.get("host") or data.get("input")
        if not host_name:
            return

        host = await uow.hosts.ensure(
            program_id=program_id,
            host=host_name,
        )

        # -------- IP (main) --------
        host_ip = data.get("host_ip")
        if not host_ip:
            return

        ip = await uow.ips.ensure(
            program_id=program_id,
            address=host_ip,
        )

        await uow.host_ips.ensure(
            host_id=host.id,
            ip_id=ip.id,
            source="httpx",
        )

        # -------- IPs from DNS (A records) --------
        for extra_ip in data.get("a", []):
            ip2 = await uow.ips.ensure(
                program_id=program_id,
                address=extra_ip,
            )

            await uow.host_ips.ensure(
                host_id=host.id,
                ip_id=ip2.id,
                source="httpx-dns",
            )

        # -------- Service --------
        scheme = data.get("scheme", "http")
        port = int(data.get("port", 80))
        technologies = {
            tech: True for tech in data.get("tech", [])
        }

        service = await uow.services.ensure(
            ip_id=ip.id,
            scheme=scheme,
            port=port,
            technologies=technologies,
        )

        # -------- Endpoint --------
        raw_path = data.get("path") or "/"
        normalized_path = raw_path.lower()
        method = data.get("method", "GET")
        status_code = data.get("status_code")

        endpoint = await uow.endpoints.ensure(
            host_id=host.id,
            service_id=service.id,
            path=raw_path,
            normalized_path=normalized_path,
            method=method,
            status_code=status_code,
        )

        # -------- Query params --------
        await self._process_query_params(
            uow=uow,
            endpoint_id=endpoint.id,
            service_id=service.id,
            raw_path=raw_path,
        )

    async def _process_query_params(
        self,
        uow: HTTPXUnitOfWork,
        endpoint_id: UUID,
        service_id: UUID,
        raw_path: str,
    ) -> None:
        """
        Extract and persist query parameters from URL path.
        """

        if "?" not in raw_path:
            return

        _, query = raw_path.split("?", 1)
        if not query:
            return

        for part in query.split("&"):
            if "=" in part:
                name, value = part.split("=", 1)
            else:
                name, value = part, ""

            if not name:
                continue

            await uow.input_parameters.ensure(
                endpoint_id=endpoint_id,
                service_id=service_id,
                name=name,
                location="query",
                example_value=value,
            )

    # =========================
    # HTTPX execution
    # =========================

    async def _execute_httpx_scan(
        self,
        targets: List[str] | str,
        timeout: int,
    ) -> AsyncIterator[Dict[str, Any]]:

        tool_path = self.settings.get_tool_path("httpx")

        command = [
            tool_path,
            "-json",
            "-silent",
            "-status-code",
            "-tech-detect",
            "-title",
            "-ip",
            "-cdn",
            "-asn",
            "-follow-redirects",
            "-filter-duplicates",
            "-s"
        ]

        stdin_input = None
        if isinstance(targets, str):
            command += ["-u", targets]
        else:
            stdin_input = "\n".join(targets)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin_input else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if stdin_input:
            process.stdin.write(stdin_input.encode())
            await process.stdin.drain()
            process.stdin.close()

        async for line in process.stdout:
            try:
                yield json.loads(line.decode().strip())
            except json.JSONDecodeError:
                continue

        await process.wait()
