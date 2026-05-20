"""FastAPI application with DI, EventBus and Orchestrator setup"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka

from api.config import Settings
from api.infrastructure.adapters.mappers import start_mappers
from api.application.container import create_container
from api.presentation.rest.handlers import (
    global_exception_handler,
    scan_execution_handler,
    tool_not_found_handler
)
from api.presentation.rest.routes import router
from api.application.exceptions import ScanExecutionError, ToolNotFoundError

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: initialize DB, mappers, EventBus and Orchestrator"""
    container = app.state.dishka_container
    settings: Settings = app.state.settings

    try:
        start_mappers()

        from api.application.pipeline.registry import NodeRegistry
        registry: NodeRegistry = await container.get(NodeRegistry)
        await registry.start()  

        if settings.USE_SCHEDULER:
            from api.application.scheduler import ActionScheduler, load_scheduler_config
            from api.application.services.action import ActionService
            from api.application.services.policy import PolicyService
            from api.infrastructure.events.event_bus import EventBus
            from api.infrastructure.orchestration.store import OrchestrationStore

            event_bus: EventBus = await container.get(EventBus)
            orchestration_store: OrchestrationStore = await container.get(OrchestrationStore)
            action_service = ActionService(
                event_bus=event_bus,
                store=orchestration_store,
                policy=PolicyService(),
            )
            scheduler_config = load_scheduler_config(settings.SCHEDULER_CONFIG_PATH)
            scheduler = ActionScheduler(
                action_service,
                scheduler_config,
                tick_seconds=settings.SCHEDULER_TICK_SECONDS,
            )
            scheduler.start()
            app.state.action_scheduler = scheduler

        logger.info("Application startup complete")
    except Exception as e:
        logger.exception("Startup failed: %s", e)
        raise e

    yield

    scheduler = getattr(app.state, "action_scheduler", None)
    if scheduler is not None:
        await scheduler.stop()

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
    app.state.settings = settings

    app.add_exception_handler(ToolNotFoundError, tool_not_found_handler)
    app.add_exception_handler(ScanExecutionError, scan_execution_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    setup_dishka(container, app)
    app.include_router(router)
    logging.basicConfig(level=settings.LOG_LEVEL)

    return app
