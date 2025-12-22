"""Global Exception Handlers"""
from fastapi import Request, status
from fastapi.responses import JSONResponse

from ...application.exceptions import ScanExecutionError, ToolNotFoundError


async def tool_not_found_handler(request: Request, exc: ToolNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": f"Scanner tool '{exc.tool_name}' not found at path: {exc.path}. Please check volume mounts.",
            "code": "TOOL_NOT_FOUND"
        }
    )

async def scan_execution_handler(request: Request, exc: ScanExecutionError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": f"Scan execution failed: {str(exc)}",
            "code": "SCAN_FAILED"
        }
    )

async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal Server Error",
            "code": "INTERNAL_ERROR"
        }
    )