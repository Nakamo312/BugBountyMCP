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
    """
    container: AsyncContainer = request.app.state.dishka_container
    db_connection: DatabaseConnection = await container.get(DatabaseConnection)
    
    async with db_connection.session() as session:
        # Add session to container context for this request
        async with container(
            context={AsyncSession: session},
        ):
            response = await call_next(request)
            return response

