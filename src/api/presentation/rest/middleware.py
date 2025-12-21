"""FastAPI middleware for DI container"""
from typing import Callable
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from dishka import AsyncContainer

from ...infrastructure.database.connection import DatabaseConnection


async def db_session_middleware(
    request: Request,
    call_next: Callable,
) -> Response:
    """
    Middleware to provide database session for each request.
    Session is added to container context and automatically injected.
    This middleware runs AFTER dishka's ContainerMiddleware.
    """
    container: AsyncContainer = request.app.state.dishka_container
    db_connection: DatabaseConnection = await container.get(DatabaseConnection)
    
    async with db_connection.session() as session:
        # Get the request container created by dishka's ContainerMiddleware
        # It should be in request.state after ContainerMiddleware runs
        request_container = getattr(request.state, 'dishka_container', None)
        
        if request_container:
            # Add session to the existing request container's context
            async with request_container(context={AsyncSession: session}):
                response = await call_next(request)
        else:
            # Fallback: if container not found, create nested container
            async with container(context={AsyncSession: session}):
                response = await call_next(request)
        
        return response

