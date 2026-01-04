"""REST API routes - Presentation layer"""
from uuid import UUID
from fastapi import APIRouter, HTTPException
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
    ScanResponse
)
from api.application.services.subfinder import SubfinderScanService
from api.application.services.httpx import HTTPXScanService
from api.application.services.gau import GAUScanService
from api.application.services.katana import KatanaScanService
from api.application.services.linkfinder import LinkFinderScanService
from api.application.services.mantra import MantraScanService
from api.application.services.ffuf import FFUFScanService
from api.application.services.dnsx import DNSxScanService


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
    response_model=ScanResponse,
    summary="Run HTTPX Scan",
    description="Starts HTTPX probing. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_httpx(
    request: HTTPXScanRequest,
    httpx_service: FromDishka[HTTPXScanService],
) -> ScanResponse:
    """
    Start HTTPX scan.

    - **program_id**: Program UUID
    - **targets**: Single target or list of targets (URLs or domains)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Results are published to EventBus for ingestion.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await httpx_service.execute(
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
    description="Starts DNSx DNS enumeration (basic or deep mode). Returns after scan completes.",
    tags=["Scans"]
)
async def scan_dnsx(
    request: DNSxScanRequest,
    dnsx_service: FromDishka[DNSxScanService],
) -> ScanResponse:
    """
    Start DNSx scan to enumerate DNS records for hosts.

    - **program_id**: Program UUID
    - **targets**: Single domain/host or list of domains/hosts to scan
    - **mode**: Scan mode - 'basic' (A/AAAA/CNAME) or 'deep' (all records including MX/TXT/NS/SOA)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns after scan completes. Discovered DNS records are ingested into database.
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
