"""Combine all routes into single router"""
from fastapi import APIRouter
from .scan import router as scan_router
from .program import router as program_router
from .host import router as host_router
from .analysis import router as analysis_router
from .proxy import router as proxy_router
from .infrastructure import router as infrastructure_router

router = APIRouter()

router.include_router(scan_router, prefix="/api/v1", tags=["Scans"])
router.include_router(program_router, prefix="/api/v1", tags=["Programs"])
router.include_router(host_router, prefix="/api/v1/hosts", tags=["Hosts"])
router.include_router(analysis_router, prefix="/api/v1/analysis", tags=["Analysis"])
router.include_router(proxy_router, prefix="/api/v1", tags=["Proxy"])
router.include_router(infrastructure_router, prefix="/api/v1/infrastructure", tags=["Infrastructure"])
