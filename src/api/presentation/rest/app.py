"""FastAPI application with DI, EventBus and Orchestrator setup"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka

from api.config import Settings
from api.infrastructure.adapters.mappers import start_mappers
from api.infrastructure.database.connection import DatabaseConnection
from api.application.container import create_container
from api.presentation.rest.handlers import (
    global_exception_handler,
    scan_execution_handler,
    tool_not_found_handler
)
from api.presentation.rest.routes import router
from src.api.application.exceptions import ScanExecutionError, ToolNotFoundError
from api.application.services.orchestrator import Orchestrator
from api.infrastructure.events.event_bus import EventBus

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: initialize DB, mappers, EventBus and Orchestrator"""
    container = app.state.dishka_container

    try:
        db_connection = await container.get(DatabaseConnection)
        await db_connection.create_tables()
        start_mappers()

        orchestrator: Orchestrator = await container.get(Orchestrator)
        await orchestrator.start()  

        logger.info("Application startup complete")
    except Exception as e:
        logger.exception("Startup failed: %s", e)
        raise e

    yield

    await container.close()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create FastAPI app with DI container, routes and exception handlers"""
    settings = Settings()
    
    container = create_container(context={Settings: settings})
    
    app = FastAPI(
        title="Bug Bounty Framework API",
        lifespan=lifespan
    )

    app.add_exception_handler(ToolNotFoundError, tool_not_found_handler)
    app.add_exception_handler(ScanExecutionError, scan_execution_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    setup_dishka(container, app)
    app.include_router(router)
    logging.basicConfig(level=settings.LOG_LEVEL)

    return app
