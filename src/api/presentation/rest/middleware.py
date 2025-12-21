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
    
    Due to LIFO stack, this runs BEFORE dishka's ContainerMiddleware.
    We create a nested container with session context, and ContainerMiddleware
    will use this nested container when creating request scope.
    """
    container: AsyncContainer = request.app.state.dishka_container
    db_connection: DatabaseConnection = await container.get(DatabaseConnection)
    
    async with db_connection.session() as session:
        # Create nested container with session in context
        # ContainerMiddleware will use the container from request.state.dishka_container
        # So we set it in request state before ContainerMiddleware runs
        async with container(context={AsyncSession: session}) as nested_container:
            # Set nested container in request state so ContainerMiddleware uses it
            request.state.dishka_container = nested_container
            try:
                response = await call_next(request)
            finally:
                # Clean up - remove container from request state
                if hasattr(request.state, 'dishka_container'):
                    delattr(request.state, 'dishka_container')
        
        return response

