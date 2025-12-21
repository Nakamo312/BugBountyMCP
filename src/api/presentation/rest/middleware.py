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
    
    Due to LIFO stack, this runs AFTER ContainerMiddleware.
    ContainerMiddleware creates request scope and stores container in request.state.dishka_container.
    We wrap that request container with session context.
    """
    container: AsyncContainer = request.app.state.dishka_container
    db_connection: DatabaseConnection = await container.get(DatabaseConnection)
    
    async with db_connection.session() as session:
        # Get the request container created by ContainerMiddleware
        # It should be in request.state after ContainerMiddleware runs
        request_container = getattr(request.state, 'dishka_container', None)
        
        if request_container:
            # Wrap request container with session context
            async with request_container(context={AsyncSession: session}) as wrapped_container:
                # Replace request container with wrapped one
                original_container = request.state.dishka_container
                request.state.dishka_container = wrapped_container
                try:
                    response = await call_next(request)
                finally:
                    # Restore original container
                    request.state.dishka_container = original_container
        else:
            # Fallback: if container not found, create nested container
            async with container(context={AsyncSession: session}):
                response = await call_next(request)
        
        return response

