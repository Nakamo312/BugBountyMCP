"""Combine all routes into single router"""
from fastapi import APIRouter
from .scan import router as scan_router
from .program import router as program_router

router = APIRouter()

router.include_router(scan_router, prefix="/api/v1", tags=["Scans"])
router.include_router(program_router, prefix="/api/v1", tags=["Programs"])