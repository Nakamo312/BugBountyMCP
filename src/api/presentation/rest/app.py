"""FastAPI application with DI setup"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka
from starlette.middleware.base import BaseHTTPMiddleware

from api.config import Settings
from api.application.exceptions import ScanExecutionError, ToolNotFoundError
from api.presentation.rest.handlers import global_exception_handler, scan_execution_handler, tool_not_found_handler

from api.application.container import create_container
from api.infrastructure.database.connection import DatabaseConnection
from api.infrastructure.adapters.mappers import start_mappers
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    container = app.state.dishka_container
    db_connection = await container.get(DatabaseConnection)
    await db_connection.create_tables()
    start_mappers()
    yield
    await container.close()


def create_app() -> FastAPI:
    settings = Settings() 
    
    container = create_container(context={Settings: settings})
    
    app = FastAPI(
        title="Bug Bounty Framework API",
        lifespan=lifespan,
    )
    app.add_exception_handler(ToolNotFoundError, tool_not_found_handler)
    app.add_exception_handler(ScanExecutionError, scan_execution_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    setup_dishka(container, app)
    
    app.include_router(router)
    return app