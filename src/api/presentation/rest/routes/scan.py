"""REST API routes - Presentation layer"""
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from api.presentation.schemas import (
    HTTPXScanRequest,
    SubfinderScanRequest,
    GAUScanRequest,
    KatanaScanRequest,
    LinkFinderScanRequest,
    MantraScanRequest,
    FFUFScanRequest,
    DNSxScanRequest,
    SubjackScanRequest,
    ASNMapScanRequest,
    MapCIDRScanRequest,
    NaabuScanRequest,
    ScanResponse
)
from api.application.services.subfinder import SubfinderScanService
from api.application.services.gau import GAUScanService
from api.application.services.katana import KatanaScanService
from api.application.services.linkfinder import LinkFinderScanService
from api.application.services.mantra import MantraScanService
from api.application.services.ffuf import FFUFScanService
from api.application.services.dnsx import DNSxScanService
from api.application.services.subjack import SubjackScanService
from api.application.services.asnmap import ASNMapScanService
from api.application.services.mapcidr import MapCIDRService
from api.application.services.naabu import NaabuScanService
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType


router = APIRouter(route_class=DishkaRoute)


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "ok", "service": "Bug Bounty Framework API"}


@router.post(
    "/scan/subfinder",
    response_model=ScanResponse,
    summary="Run Subfinder Scan",
    description="Starts Subfinder subdomain enumeration. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_subfinder(
    request: SubfinderScanRequest,
    subfinder_service: FromDishka[SubfinderScanService],
) -> ScanResponse:
    """
    Start Subfinder scan to discover subdomains.

    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered subdomains are published to EventBus for HTTPX processing.
    """
    try:
        result = await subfinder_service.execute(
            program_id=UUID(request.program_id),
            domain=request.domain
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/httpx",
    summary="Run HTTPX Scan",
    description="Starts HTTPX probing. Returns 202 Accepted immediately, scan runs asynchronously via node pipeline.",
    tags=["Scans"],
    status_code=202
)
async def scan_httpx(
    request: HTTPXScanRequest,
    event_bus: FromDishka[EventBus],
) -> JSONResponse:
    """
    Start HTTPX scan asynchronously via node pipeline.

    - **program_id**: Program UUID
    - **targets**: Single target or list of targets (URLs or domains)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via HTTPXNode.
    Results are ingested into database and trigger subsequent pipeline events.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish(
            EventType.HTTPX_SCAN_REQUESTED.value,
            {
                "_event_type": EventType.HTTPX_SCAN_REQUESTED.value,
                "program_id": request.program_id,
                "targets": targets,
            },
        )

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"HTTPX scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/gau",
    response_model=ScanResponse,
    summary="Run GAU Scan",
    description="Starts GAU URL discovery from web archives. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_gau(
    request: GAUScanRequest,
    gau_service: FromDishka[GAUScanService],
) -> ScanResponse:
    """
    Start GAU (GetAllURLs) scan to discover historical URLs.

    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **include_subs**: Include subdomains in discovery (default: true)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered URLs are published to EventBus for HTTPX processing.
    """
    try:
        result = await gau_service.execute(
            program_id=UUID(request.program_id),
            domain=request.domain,
            include_subs=request.include_subs
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/katana",
    response_model=ScanResponse,
    summary="Run Katana Scan",
    description="Starts Katana web crawling. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_katana(
    request: KatanaScanRequest,
    katana_service: FromDishka[KatanaScanService],
) -> ScanResponse:
    """
    Start Katana crawl to discover URLs via active web crawling.

    - **program_id**: Program UUID
    - **targets**: Single target URL or list of target URLs to crawl
    - **depth**: Maximum crawl depth (default: 3)
    - **js_crawl**: Enable JavaScript endpoint parsing (default: true)
    - **headless**: Enable headless browser mode (default: false)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered URLs are published to EventBus for HTTPX processing.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await katana_service.execute(
            program_id=UUID(request.program_id),
            targets=targets,
            depth=request.depth,
            js_crawl=request.js_crawl,
            headless=request.headless
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/linkfinder",
    response_model=ScanResponse,
    summary="Run LinkFinder Scan",
    description="Starts LinkFinder JS analysis to discover hidden endpoints. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_linkfinder(
    request: LinkFinderScanRequest,
    linkfinder_service: FromDishka[LinkFinderScanService],
) -> ScanResponse:
    """
    Start LinkFinder scan to extract endpoints from JavaScript files.

    - **program_id**: Program UUID
    - **targets**: Single JS URL or list of JS URLs to analyze
    - **timeout**: Scan timeout per JS file in seconds (default: 15)

    Returns immediately. Discovered URLs are validated against program scope and ingested as endpoints.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await linkfinder_service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/mantra",
    response_model=ScanResponse,
    summary="Run Mantra Scan",
    description="Starts Mantra secret scanning on JavaScript files. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_mantra(
    request: MantraScanRequest,
    mantra_service: FromDishka[MantraScanService],
) -> ScanResponse:
    """
    Start Mantra scan to discover leaked secrets and credentials in JavaScript files.

    - **program_id**: Program UUID
    - **targets**: Single JS URL or list of JS URLs to scan for secrets
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns immediately. Discovered secrets are published to EventBus and stored in leaks table with endpoint association.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await mantra_service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/ffuf",
    response_model=ScanResponse,
    summary="Run FFUF Scan",
    description="Starts FFUF directory/file fuzzing. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_ffuf(
    request: FFUFScanRequest,
    ffuf_service: FromDishka[FFUFScanService],
) -> ScanResponse:
    """
    Start FFUF scan to discover hidden directories and files via fuzzing.

    - **program_id**: Program UUID
    - **targets**: Single base URL or list of URLs to fuzz
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered endpoints are published to EventBus and ingested with scope validation.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await ffuf_service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/dnsx",
    response_model=ScanResponse,
    summary="Run DNSx Scan",
    description="Starts DNSx DNS enumeration (basic, deep, or ptr mode). Returns after scan completes.",
    tags=["Scans"]
)
async def scan_dnsx(
    request: DNSxScanRequest,
    dnsx_service: FromDishka[DNSxScanService],
) -> ScanResponse:
    """
    Start DNSx scan to enumerate DNS records for hosts or reverse lookup for IPs.

    - **program_id**: Program UUID
    - **targets**: Single domain/host or list of domains/hosts (for basic/deep), OR IP addresses (for ptr mode)
    - **mode**: Scan mode - 'basic' (A/AAAA/CNAME), 'deep' (all records including MX/TXT/NS/SOA), or 'ptr' (reverse DNS)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns after scan completes. Discovered DNS records are ingested into database.
    PTR mode discovers new hosts from IP addresses and triggers subdomain enumeration pipeline.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await dnsx_service.execute(
            program_id=UUID(request.program_id),
            targets=targets,
            mode=request.mode
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/subjack",
    response_model=ScanResponse,
    summary="Run Subjack Scan",
    description="Starts Subjack subdomain takeover detection. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_subjack(
    request: SubjackScanRequest,
    subjack_service: FromDishka[SubjackScanService],
) -> ScanResponse:
    """
    Start Subjack scan to detect subdomain takeover vulnerabilities.

    - **program_id**: Program UUID
    - **targets**: Single domain or list of domains to check for takeover
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns immediately. Discovered vulnerabilities are published to EventBus and stored as findings.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await subjack_service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/asnmap",
    response_model=ScanResponse,
    summary="Run ASNMap Scan",
    description="Starts ASNMap ASN/CIDR enumeration. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_asnmap(
    request: ASNMapScanRequest,
    asnmap_service: FromDishka[ASNMapScanService],
) -> ScanResponse:
    """
    Start ASNMap scan to enumerate ASN and CIDR ranges.

    - **program_id**: Program UUID
    - **targets**: Domains (mode=domain), ASN numbers (mode=asn), or organization names (mode=organization)
    - **mode**: Scan mode - 'domain', 'asn', or 'organization' (default: domain)
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns immediately. Discovered ASNs and CIDR blocks are ingested into database.
    Publishes ASN_DISCOVERED and CIDR_DISCOVERED events for further processing.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await asnmap_service.execute(
            program_id=UUID(request.program_id),
            targets=targets,
            mode=request.mode
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/mapcidr",
    response_model=ScanResponse,
    summary="Run MapCIDR Operation",
    description="Performs CIDR operations (expand, slice, aggregate). Returns immediately.",
    tags=["Scans"]
)
async def scan_mapcidr(
    request: MapCIDRScanRequest,
    mapcidr_service: FromDishka[MapCIDRService],
) -> ScanResponse:
    """
    Perform MapCIDR operations on CIDR blocks.

    - **program_id**: Program UUID
    - **cidrs**: Single CIDR or list of CIDRs to process
    - **operation**: Operation type - 'expand', 'slice_count', 'slice_host', 'aggregate'
    - **count**: For slice_count - number of subnets to create
    - **host_count**: For slice_host - target hosts per subnet
    - **skip_base**: Skip base IPs ending in .0
    - **skip_broadcast**: Skip broadcast IPs ending in .255
    - **shuffle**: Shuffle IPs in random order
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns immediately. Results published to EventBus for further processing.
    """
    try:
        cidrs = request.cidrs if isinstance(request.cidrs, list) else [request.cidrs]
        program_id = UUID(request.program_id)

        if request.operation == "expand":
            result = await mapcidr_service.expand(
                program_id=program_id,
                cidrs=cidrs,
                skip_base=request.skip_base,
                skip_broadcast=request.skip_broadcast,
                shuffle=request.shuffle
            )
        elif request.operation == "slice_count":
            if not request.count:
                raise ValueError("count parameter required for slice_count operation")
            result = await mapcidr_service.slice_by_count(
                program_id=program_id,
                cidrs=cidrs,
                count=request.count
            )
        elif request.operation == "slice_host":
            if not request.host_count:
                raise ValueError("host_count parameter required for slice_host operation")
            result = await mapcidr_service.slice_by_host_count(
                program_id=program_id,
                cidrs=cidrs,
                host_count=request.host_count
            )
        elif request.operation == "aggregate":
            result = await mapcidr_service.aggregate(
                program_id=program_id,
                ips=cidrs
            )
        else:
            raise ValueError(f"Invalid operation: {request.operation}")

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/naabu",
    response_model=ScanResponse,
    summary="Run Naabu Port Scan",
    description="Starts Naabu port scanning (active, passive, or nmap mode). Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_naabu(
    request: NaabuScanRequest,
    naabu_service: FromDishka[NaabuScanService],
) -> ScanResponse:
    """
    Start Naabu port scan to discover open ports and services.

    - **program_id**: Program UUID
    - **targets**: Single host/IP or list of hosts/IPs to scan
    - **scan_mode**: Scan mode - 'active' (default), 'passive', or 'nmap'
    - **ports**: Port specification (e.g., "80,443,8080-8090") or None for top-ports
    - **top_ports**: Top ports preset - "100", "1000" (default), "full"
    - **rate**: Packets per second (default: 1000)
    - **scan_type**: Scan type - "s" (SYN) or "c" (CONNECT, default)
    - **exclude_cdn**: Skip full port scans for CDN/WAF, only scan 80,443 (default: true)
    - **nmap_cli**: Nmap command for service detection (nmap mode only, default: "nmap -sV")
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered open ports are published to EventBus and ingested into database.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]
        program_id = UUID(request.program_id)

        if request.scan_mode == "active":
            result = await naabu_service.execute(
                program_id=program_id,
                hosts=targets,
                ports=request.ports,
                top_ports=request.top_ports,
                rate=request.rate,
                scan_type=request.scan_type,
                exclude_cdn=request.exclude_cdn
            )
        elif request.scan_mode == "passive":
            result = await naabu_service.execute_passive(
                program_id=program_id,
                hosts=targets
            )
        elif request.scan_mode == "nmap":
            result = await naabu_service.execute_with_nmap(
                program_id=program_id,
                hosts=targets,
                nmap_cli=request.nmap_cli,
                top_ports=request.top_ports,
                rate=request.rate
            )
        else:
            raise ValueError(f"Invalid scan_mode: {request.scan_mode}. Must be 'active', 'passive', or 'nmap'")

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
