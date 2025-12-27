"""REST API routes - Presentation layer"""
from uuid import UUID
from fastapi import APIRouter, HTTPException
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from api.presentation.schemas import (
    HTTPXScanRequest,
    SubfinderScanRequest,
    ScanResponse
)
from api.application.dto import (
    HTTPXScanInputDTO,
    SubfinderScanInputDTO,
)
from api.application.services.subfinder import SubfinderScanService
from api.application.services.httpx import HTTPXScanService


router = APIRouter(route_class=DishkaRoute)


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "ok", "service": "Bug Bounty Framework API"}


@router.post(
    "/scan/subfinder",
    response_model=ScanResponse,
    summary="Run Subfinder Scan",
    description="Executes Subfinder to discover subdomains for a given target.",
    tags=["Scans"]
)
async def scan_subfinder(
    request: SubfinderScanRequest,
    subfinder_service: FromDishka[SubfinderScanService],
) -> ScanResponse:
    """
    Execute Subfinder scan to discover subdomains.
    
    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **probe**: If True, probe discovered subdomains with HTTPX (default: True)
    - **timeout**: Scan timeout in seconds (default: 600)
    """
    try:
        input_dto = SubfinderScanInputDTO(
            program_id=UUID(request.program_id),
            domain=request.domain,
            probe=request.probe,
            timeout=request.timeout
        )
        
        result = await subfinder_service.execute(input_dto)
        
        return ScanResponse(
            status="success",
            message=f"Subfinder scan completed for {request.domain}",
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/httpx",
    response_model=ScanResponse,
    summary="Run HTTPX Scan",
    description="Executes HTTPX probing on a list of targets.",
    tags=["Scans"]
)
async def scan_httpx(
    request: HTTPXScanRequest,
    httpx_service: FromDishka[HTTPXScanService],
) -> ScanResponse:
    """
    Execute HTTPX scan.
    
    - **program_id**: Program UUID
    - **targets**: Single target or list of targets (URLs or domains)
    - **timeout**: Scan timeout in seconds (default: 600)
    """
    try:
        input_dto = HTTPXScanInputDTO(
            program_id=request.program_id,
            targets=request.targets,
            timeout=request.timeout
        )
        
        result = await httpx_service.execute(
            program_id=input_dto.program_id,
            targets=input_dto.targets
        )

        
        return ScanResponse(
            status="success",
            message="HTTPX scan completed",
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
