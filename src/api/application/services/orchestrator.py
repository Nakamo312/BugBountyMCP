from typing import Dict, Any, List, Tuple
import asyncio
import logging
from uuid import UUID
from dishka import AsyncContainer

from api.application.services.base_service import ScopeCheckMixin
from api.config import Settings
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.application.services.httpx import HTTPXScanService
from api.application.services.katana import KatanaScanService
from api.application.services.linkfinder import LinkFinderScanService
from api.application.services.mantra import MantraScanService
from api.application.services.dnsx import DNSxScanService
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.ingestors.dnsx_ingestor import DNSxResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(
        self,
        bus: EventBus,
        container: AsyncContainer,
        settings: Settings,
    ):
        self.bus = bus
        self.container = container
        self.settings = settings
        self.tasks: set[asyncio.Task] = set()
        self._scan_semaphore = asyncio.Semaphore(settings.ORCHESTRATOR_MAX_CONCURRENT)

    async def _filter_by_scope(self, program_id: UUID, targets: List[str]) -> Tuple[List[str], List[str]]:
        """
        Filter targets by program scope rules.

        Args:
            program_id: Program UUID
            targets: List of domains or URLs to filter

        Returns:
            Tuple of (in_scope_targets, out_of_scope_targets)
        """
        async with self.container() as request_container:
            program_uow = await request_container.get(ProgramUnitOfWork)
            async with program_uow:
                scope_rules = await program_uow.scope_rules.find_by_program(program_id)
                return ScopeCheckMixin.filter_in_scope(targets, scope_rules)

    async def start(self):
        await self.bus.connect()
        asyncio.create_task(
            self.bus.subscribe(EventType.SERVICE_EVENTS, self.handle_service_event)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.SCAN_RESULTS_BATCH, self.handle_scan_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.SUBDOMAIN_DISCOVERED, self.handle_subdomain_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.GAU_DISCOVERED, self.handle_gau_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.KATANA_RESULTS_BATCH, self.handle_katana_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.HOST_DISCOVERED, self.handle_host_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.JS_FILES_DISCOVERED, self.handle_js_files_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.MANTRA_RESULTS_BATCH, self.handle_mantra_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.FFUF_RESULTS_BATCH, self.handle_ffuf_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.DNSX_BASIC_RESULTS_BATCH, self.handle_dnsx_basic_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.DNSX_DEEP_RESULTS_BATCH, self.handle_dnsx_deep_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.DNSX_PTR_RESULTS_BATCH, self.handle_dnsx_ptr_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.DNSX_FILTERED_HOSTS, self.handle_dnsx_filtered_hosts)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.CNAME_DISCOVERED, self.handle_cname_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.SUBJACK_RESULTS_BATCH, self.handle_subjack_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.ASNMAP_RESULTS_BATCH, self.handle_asnmap_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.ASN_DISCOVERED, self.handle_asn_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.CIDR_DISCOVERED, self.handle_cidr_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.IPS_EXPANDED, self.handle_ips_expanded)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.NAABU_RESULTS_BATCH, self.handle_naabu_results_batch)
        )

    async def handle_service_event(self, event: Dict[str, Any]):
        async with self.container() as request_container:
            httpx_service = await request_container.get(HTTPXScanService)

            action = event.get("action", "execute")
            kwargs = {k: v for k, v in event.items() if k not in ("service", "action")}

            await getattr(httpx_service, action)(**kwargs)

    async def handle_scan_results_batch(self, event: Dict[str, Any]):
        """
        Handle HTTPX results: ingest, publish live hosts for DNSx Deep.
        Pipeline step 3: Subfinder -> DNSx Basic -> HTTPX -> DNSx Deep
        """
        program_id = UUID(event["program_id"])
        results = event["results"]

        logger.info(f"Ingesting HTTPX results batch: program={program_id} count={len(results)}")

        async with self.container() as request_container:
            ingestor = await request_container.get(HTTPXResultIngestor)
            await ingestor.ingest(program_id, results)

        live_hosts = list({r.get("host") for r in results if r.get("host") and r.get("status_code")})

        if live_hosts:
            logger.info(f"Publishing live hosts for DNSx Deep: program={program_id} count={len(live_hosts)}")
            await self.bus.publish(
                EventType.HOST_DISCOVERED,
                {
                    "program_id": str(program_id),
                    "hosts": live_hosts,
                    "source": "httpx_for_dnsx_deep"
                }
            )

    async def handle_subdomain_discovered(self, event: Dict[str, Any]):
        """
        Handle subdomain discovery events by triggering DNSx Basic (wildcard filter) then HTTPX.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        targets = event["subdomains"]

        logger.info(f"Received subdomain batch for program {program_id}: {len(targets)} targets")

        task = asyncio.create_task(self._process_subdomain_batch(program_id, targets))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_subdomain_batch(self, program_id: str, targets: list[str]):
        """
        Process subdomain batch: DNSx Basic (wildcard filter) -> filter -> HTTPX.
        Filters subdomains by scope before scanning.
        """
        program_uuid = UUID(program_id)
        in_scope, out_of_scope = await self._filter_by_scope(program_uuid, targets)

        if out_of_scope:
            logger.info(
                f"Filtered out-of-scope subdomains: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            logger.info(f"No in-scope subdomains to scan: program={program_id}")
            return

        async with self._scan_semaphore:
            async with self.container() as request_container:
                dnsx_service = await request_container.get(DNSxScanService)

                logger.info(f"Starting DNSx Basic scan for program {program_id}: {len(in_scope)} targets")

                await dnsx_service.execute(program_id=program_uuid, targets=in_scope, mode="basic")

    async def handle_gau_discovered(self, event: Dict[str, Any]):
        """
        Handle GAU URL discovery events by triggering HTTPX scans for the batch.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        urls = event["urls"]

        logger.info(f"Received GAU URL batch for program {program_id}: {len(urls)} URLs")

        task = asyncio.create_task(self._process_gau_batch(program_id, urls))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_gau_batch(self, program_id: str, urls: list[str]):
        """
        Process GAU URL batch with semaphore to limit concurrent scans.
        Filters URLs by scope before scanning.
        """
        program_uuid = UUID(program_id)
        in_scope, out_of_scope = await self._filter_by_scope(program_uuid, urls)

        if out_of_scope:
            logger.info(
                f"Filtered out-of-scope URLs: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            logger.info(f"No in-scope URLs to scan: program={program_id}")
            return

        async with self._scan_semaphore:
            async with self.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                logger.info(f"Starting HTTPX scan for GAU batch: program={program_id} urls={len(in_scope)}")

                await httpx_service.execute(program_id=program_id, targets=in_scope)

    async def handle_katana_results_batch(self, event: Dict[str, Any]):
        """Handle batched Katana scan results"""
        try:
            async with self.container() as request_container:
                ingestor = await request_container.get(KatanaResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting Katana results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"Katana results ingested successfully: program={program_id} count={len(results)}")
        except Exception as exc:
            logger.error(f"Failed to ingest Katana results: error={exc}", exc_info=True)

    async def handle_mantra_results_batch(self, event: Dict[str, Any]):
        """Handle batched Mantra scan results"""
        try:
            async with self.container() as request_container:
                ingestor = await request_container.get(MantraResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting Mantra results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"Mantra results ingested successfully: program={program_id} count={len(results)}")
        except Exception as exc:
            logger.error(f"Failed to ingest Mantra results: error={exc}", exc_info=True)

    async def handle_host_discovered(self, event: Dict[str, Any]):
        """
        Handle new host discovery events by triggering Katana crawls or DNSx Deep.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        hosts = event["hosts"]
        source = event.get("source", "httpx")

        logger.info(f"Received new hosts for program {program_id}: {len(hosts)} hosts source={source}")

        if source == "httpx_for_dnsx_deep":
            task = asyncio.create_task(self._process_dnsx_deep_batch(program_id, hosts))
        else:
            task = asyncio.create_task(self._process_host_batch(program_id, hosts))

        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_host_batch(self, program_id: str, hosts: list[str]):
        """
        Process new host batch by launching Katana crawl with rate limiting.
        Filters hosts by scope before crawling.
        Delay prevents cascading load from newly discovered hosts.
        """
        await asyncio.sleep(self.settings.ORCHESTRATOR_SCAN_DELAY)

        program_uuid = UUID(program_id)
        in_scope, out_of_scope = await self._filter_by_scope(program_uuid, hosts)

        if out_of_scope:
            logger.info(
                f"Filtered out-of-scope hosts: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            logger.info(f"No in-scope hosts to crawl: program={program_id}")
            return

        async with self._scan_semaphore:
            async with self.container() as request_container:
                katana_service = await request_container.get(KatanaScanService)

                logger.info(f"Starting Katana crawl for new hosts: program={program_id} hosts={len(in_scope)}")

                await katana_service.execute(program_id=program_id, targets=in_scope)

    async def handle_js_files_discovered(self, event: Dict[str, Any]):
        """
        Handle JS files discovery events by triggering LinkFinder scans.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        js_files = event["js_files"]

        logger.info(f"Received JS files batch for program {program_id}: {len(js_files)} files")

        task = asyncio.create_task(self._process_js_files_batch(program_id, js_files))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_js_files_batch(self, program_id: str, js_files: list[str]):
        """
        Process JS files batch with semaphore to limit concurrent scans.
        Filters JS files by scope before scanning.
        """
        program_uuid = UUID(program_id)
        in_scope, out_of_scope = await self._filter_by_scope(program_uuid, js_files)

        if out_of_scope:
            logger.info(
                f"Filtered out-of-scope JS files: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            logger.info(f"No in-scope JS files to scan: program={program_id}")
            return

        async with self._scan_semaphore:
            async with self.container() as request_container:
                linkfinder_service = await request_container.get(LinkFinderScanService)
                mantra_service = await request_container.get(MantraScanService)

                logger.info(f"Starting LinkFinder and Mantra scans for program {program_id}: {len(in_scope)} JS files")

                await linkfinder_service.execute(program_id=program_id, targets=in_scope)
                await mantra_service.execute(program_id=program_id, targets=in_scope)

    async def handle_ffuf_results_batch(self, event: Dict[str, Any]):
        """Handle batched FFUF scan results"""
        try:
            async with self.container() as request_container:
                ingestor = await request_container.get(FFUFResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting FFUF results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"FFUF results ingested successfully: program={program_id} count={len(results)}")
        except Exception as exc:
            logger.error(f"Failed to ingest FFUF results: error={exc}", exc_info=True)

    async def handle_dnsx_basic_results_batch(self, event: Dict[str, Any]):
        """
        Handle DNSx Basic results: ingest, filter wildcard, publish filtered hosts for HTTPX.
        Pipeline step 2: Subfinder -> DNSx Basic -> HTTPX
        """
        try:
            program_id = UUID(event["program_id"])
            results = event["results"]

            logger.info(f"Processing DNSx basic results batch: program={program_id} count={len(results)}")

            async with self.container() as request_container:
                ingestor = await request_container.get(DNSxResultIngestor)
                await ingestor.ingest(program_id, results)

            non_wildcard_hosts = [
                r["host"] for r in results
                if not r.get("wildcard", False) and r.get("host")
            ]

            wildcard_count = len(results) - len(non_wildcard_hosts)

            logger.info(
                f"DNSx Basic filtering: program={program_id} "
                f"total={len(results)} wildcard={wildcard_count} real={len(non_wildcard_hosts)}"
            )

            if non_wildcard_hosts:
                await self.bus.publish(
                    EventType.DNSX_FILTERED_HOSTS,
                    {
                        "program_id": str(program_id),
                        "hosts": non_wildcard_hosts
                    }
                )

        except Exception as exc:
            logger.error(f"Failed to process DNSx basic results: error={exc}", exc_info=True)

    async def handle_dnsx_deep_results_batch(self, event: Dict[str, Any]):
        """Handle batched DNSx deep scan results and trigger Subjack for CNAME records"""
        try:
            async with self.container() as request_container:
                ingestor = await request_container.get(DNSxResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting DNSx deep results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"DNSx deep results ingested successfully: program={program_id} count={len(results)}")

                cname_hosts = []
                for result in results:
                    if result.get("cname") and not result.get("wildcard", False):
                        host = result.get("host")
                        if host:
                            cname_hosts.append(host)

                if cname_hosts:
                    logger.info(f"Publishing CNAME hosts for Subjack: program={program_id} count={len(cname_hosts)}")
                    await self.bus.publish(
                        EventType.CNAME_DISCOVERED,
                        {
                            "program_id": str(program_id),
                            "hosts": cname_hosts
                        }
                    )
        except Exception as exc:
            logger.error(f"Failed to ingest DNSx deep results: error={exc}", exc_info=True)

    async def handle_dnsx_ptr_results_batch(self, event: Dict[str, Any]):
        """
        Handle batched DNSx PTR (reverse DNS) scan results.
        Discovers new hosts from IP addresses and publishes them for further processing.
        Pipeline: CIDR expansion -> DNSx PTR -> New hosts discovered
        """
        try:
            async with self.container() as request_container:
                ingestor = await request_container.get(DNSxResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting DNSx PTR results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"DNSx PTR results ingested successfully: program={program_id} count={len(results)}")

                discovered_hosts = []
                for result in results:
                    ptr_records = result.get("ptr", [])
                    for ptr in ptr_records:
                        if ptr and ptr not in discovered_hosts:
                            discovered_hosts.append(ptr)

                if discovered_hosts:
                    logger.info(f"Publishing PTR-discovered hosts: program={program_id} count={len(discovered_hosts)}")
                    await self.bus.publish(
                        EventType.SUBDOMAIN_DISCOVERED,
                        {
                            "program_id": str(program_id),
                            "subdomains": discovered_hosts
                        }
                    )
        except Exception as exc:
            logger.error(f"Failed to ingest DNSx PTR results: error={exc}", exc_info=True)

    async def handle_dnsx_filtered_hosts(self, event: Dict[str, Any]):
        """
        Handle DNSx filtered hosts by triggering HTTPX scan.
        Pipeline step 2.5: DNSx Basic -> HTTPX
        """
        program_id = event["program_id"]
        hosts = event["hosts"]

        logger.info(f"Received DNSx filtered hosts for program {program_id}: {len(hosts)} hosts")

        task = asyncio.create_task(self._process_filtered_hosts_batch(program_id, hosts))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_filtered_hosts_batch(self, program_id: str, hosts: list[str]):
        """Process DNSx filtered hosts by launching HTTPX scan"""
        async with self._scan_semaphore:
            async with self.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                logger.info(f"Starting HTTPX scan for filtered hosts: program={program_id} hosts={len(hosts)}")

                await httpx_service.execute(program_id=program_id, targets=hosts)

    async def _process_dnsx_deep_batch(self, program_id: str, hosts: list[str]):
        """Process live hosts by launching DNSx Deep scan"""
        async with self._scan_semaphore:
            async with self.container() as request_container:
                dnsx_service = await request_container.get(DNSxScanService)

                logger.info(f"Starting DNSx Deep scan for live hosts: program={program_id} hosts={len(hosts)}")

                await dnsx_service.execute(
                    program_id=UUID(program_id),
                    targets=hosts,
                    mode="deep"
                )

    async def handle_cname_discovered(self, event: Dict[str, Any]):
        """
        Handle CNAME records by triggering Subjack scan for subdomain takeover.
        Pipeline step: DNSx Deep -> Subjack
        """
        program_id = event["program_id"]
        hosts = event["hosts"]

        logger.info(f"CNAME records discovered, launching Subjack: program={program_id} hosts={len(hosts)}")

        task = asyncio.create_task(self._process_subjack_batch(program_id, hosts))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_subjack_batch(self, program_id: str, hosts: list[str]):
        """Process CNAME hosts by launching Subjack scan"""
        async with self._scan_semaphore:
            async with self.container() as request_container:
                from api.application.services.subjack import SubjackScanService
                subjack_service = await request_container.get(SubjackScanService)

                logger.info(f"Starting Subjack scan for CNAME hosts: program={program_id} hosts={len(hosts)}")

                await subjack_service.execute(
                    program_id=UUID(program_id),
                    targets=hosts
                )

    async def handle_subjack_results_batch(self, event: Dict[str, Any]):
        """Handle batched Subjack subdomain takeover results"""
        try:
            async with self.container() as request_container:
                from api.infrastructure.ingestors.subjack_ingestor import SubjackResultIngestor
                ingestor = await request_container.get(SubjackResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting Subjack results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"Subjack results ingested successfully: program={program_id} count={len(results)}")
        except Exception as exc:
            logger.error(f"Failed to ingest Subjack results: error={exc}", exc_info=True)

    async def handle_asnmap_results_batch(self, event: Dict[str, Any]):
        """Handle batched ASNMap results"""
        try:
            async with self.container() as request_container:
                ingestor = await request_container.get(ASNMapResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]

                logger.info(f"Ingesting ASNMap results batch: program={program_id} count={len(results)}")
                await ingestor.ingest(program_id, results)
                logger.info(f"ASNMap results ingested successfully: program={program_id} count={len(results)}")
        except Exception as exc:
            logger.error(f"Failed to ingest ASNMap results: error={exc}", exc_info=True)

    async def handle_asn_discovered(self, event: Dict[str, Any]):
        """Handle ASN discovered - future: trigger additional ASN queries"""
        program_id = UUID(event["program_id"])
        asns = event["asns"]
        logger.info(f"ASN discovered event received: program={program_id} count={len(asns)}")

    async def handle_cidr_discovered(self, event: Dict[str, Any]):
        """Handle CIDR discovered - future: trigger mapcidr IP expansion"""
        program_id = UUID(event["program_id"])
        cidrs = event["cidrs"]
        logger.info(f"CIDR discovered event received: program={program_id} count={len(cidrs)}")

    async def handle_ips_expanded(self, event: Dict[str, Any]):
        """
        Handle IPS_EXPANDED event by triggering parallel HTTPx probe + Naabu port scan.
        Pipeline: MapCIDR expand -> HTTPx + Naabu (parallel)
        """
        program_id = event["program_id"]
        ips = event["ips"]
        source_cidrs = event.get("source_cidrs", [])

        logger.info(
            f"IPs expanded from CIDRs, launching parallel HTTPx + Naabu: "
            f"program={program_id} ips={len(ips)} source_cidrs={len(source_cidrs)}"
        )

        task = asyncio.create_task(self._process_expanded_ips(program_id, ips))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_expanded_ips(self, program_id: str, ips: list[str]):
        """
        Process expanded IPs with parallel HTTPx probe and Naabu port scan.
        Both tools run simultaneously on the same IP list.
        """
        program_uuid = UUID(program_id)

        async with self._scan_semaphore:
            async with self.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)
                from api.application.services.naabu import NaabuScanService
                naabu_service = await request_container.get(NaabuScanService)

                logger.info(
                    f"Starting parallel HTTPx + Naabu scans: program={program_id} ips={len(ips)}"
                )

                await asyncio.gather(
                    httpx_service.execute(program_id=program_id, targets=ips),
                    naabu_service.execute(
                        program_id=program_uuid,
                        hosts=ips,
                        top_ports="1000",
                        rate=1000,
                        scan_type="c",
                        exclude_cdn=True
                    ),
                    return_exceptions=True
                )

                logger.info(
                    f"Parallel HTTPx + Naabu scans completed: program={program_id} ips={len(ips)}"
                )

    async def handle_naabu_results_batch(self, event: Dict[str, Any]):
        """Handle batched Naabu port scan results"""
        try:
            async with self.container() as request_container:
                from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
                ingestor = await request_container.get(NaabuResultIngestor)
                program_id = UUID(event["program_id"])
                results = event["results"]
                scan_mode = event.get("scan_mode", "active")

                logger.info(
                    f"Ingesting Naabu results batch: program={program_id} "
                    f"count={len(results)} mode={scan_mode}"
                )
                await ingestor.ingest(results, program_id)
                logger.info(
                    f"Naabu results ingested successfully: program={program_id} "
                    f"count={len(results)} mode={scan_mode}"
                )
        except Exception as exc:
            logger.error(f"Failed to ingest Naabu results: error={exc}", exc_info=True)
