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
from api.presentation.rest.metrics import setup_metrics
from api.application.exceptions import ScanExecutionError, ToolNotFoundError

logger = logging.getLogger(__name__)


async def _start_scheduler(app: FastAPI, container, settings: Settings) -> None:
    from api.application.execution_limits import system_execution_budget
    from api.application.ports.action import (
        ActionApprovalPort,
        ActionCommandPort,
        ActionQueryPort,
        ActionResultPort,
    )
    from api.application.scheduler import ActionScheduler, load_scheduler_config
    from api.application.services.action import ActionService
    from api.application.services.action_catalog import ActionCatalogService
    from api.application.services.policy import PolicyService
    from api.infrastructure.repositories.adapters.scope_rule import SQLAlchemyScopeRuleRepository

    action_commands: ActionCommandPort = await container.get(ActionCommandPort)
    action_queries: ActionQueryPort = await container.get(ActionQueryPort)
    action_results: ActionResultPort = await container.get(ActionResultPort)
    action_approvals: ActionApprovalPort = await container.get(ActionApprovalPort)
    catalog_service: ActionCatalogService = await container.get(ActionCatalogService)
    scope_rule_repository: SQLAlchemyScopeRuleRepository = await container.get(
        SQLAlchemyScopeRuleRepository
    )
    action_service = ActionService(
        commands=action_commands,
        queries=action_queries,
        results=action_results,
        approvals=action_approvals,
        policy=PolicyService(),
        catalog=catalog_service,
        scope_rules=scope_rule_repository,
        system_budget=system_execution_budget(settings),
    )
    scheduler_config = load_scheduler_config(settings.SCHEDULER_CONFIG_PATH)
    scheduler = ActionScheduler(
        action_service=action_service,
        catalog_service=catalog_service,
        config=scheduler_config,
        tick_seconds=settings.SCHEDULER_TICK_SECONDS,
    )
    scheduler.start()
    app.state.action_scheduler = scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: initialize DB, mappers, EventBus and Orchestrator"""
    container = app.state.dishka_container
    settings: Settings = app.state.settings

    try:
        start_mappers()

        from api.application.capability_catalog import load_tool_catalog_snapshot
        from api.application.pipeline.builder import register_manifest_nodes
        from api.application.pipeline.registry import NodeRegistry
        from api.infrastructure.runtime_manifest import ManifestActivator

        manifest = load_tool_catalog_snapshot(settings.PIPELINE_CONFIG_PATH)
        activator: ManifestActivator = await container.get(ManifestActivator)
        activation = await activator.activate(manifest)
        logger.info(
            "Runtime manifest active: snapshot=%s changed=%s entries=%s",
            activation.snapshot_id,
            activation.changed,
            activation.entry_count,
        )

        registry: NodeRegistry = await container.get(NodeRegistry)
        if settings.USE_NODE_PIPELINE:
            register_manifest_nodes(
                registry,
                settings,
                await activator.active_manifest(),
            )
        app.state.node_registry = registry
        await registry.start()

        if settings.USE_EVENT_DISPATCHER:
            from api.infrastructure.events.dispatcher import EventDispatcher

            event_dispatcher: EventDispatcher = await container.get(EventDispatcher)
            await event_dispatcher.start()
            app.state.event_dispatcher = event_dispatcher

        if settings.USE_AGENT_WAIT_PROCESSOR:
            from api.application.agent_wait_conditions import AgentWaitConditionProcessor

            wait_condition_processor: AgentWaitConditionProcessor = await container.get(
                AgentWaitConditionProcessor
            )
            await wait_condition_processor.start()
            app.state.wait_condition_processor = wait_condition_processor

        if settings.USE_AGENT_INBOX_PROCESSOR:
            from api.application.research_inbox_processor import ResearchInboxProcessor

            inbox_processor: ResearchInboxProcessor = await container.get(
                ResearchInboxProcessor
            )
            await inbox_processor.start()
            app.state.agent_inbox_processor = inbox_processor

        if settings.USE_SCHEDULER:
            await _start_scheduler(app, container, settings)

        logger.info("Application startup complete")
    except Exception as e:
        logger.exception("Startup failed: %s", e)
        raise e

    yield

    event_dispatcher = getattr(app.state, "event_dispatcher", None)
    if event_dispatcher is not None:
        await event_dispatcher.stop()

    wait_condition_processor = getattr(app.state, "wait_condition_processor", None)
    if wait_condition_processor is not None:
        await wait_condition_processor.stop()

    inbox_processor = getattr(app.state, "agent_inbox_processor", None)
    if inbox_processor is not None:
        await inbox_processor.stop()

    scheduler = getattr(app.state, "action_scheduler", None)
    if scheduler is not None:
        await scheduler.stop()

    registry = getattr(app.state, "node_registry", None)
    if registry is not None:
        await registry.stop()
        del app.state.node_registry

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
    setup_metrics(app)
    app.include_router(router)
    logging.basicConfig(level=settings.LOG_LEVEL)

    return app
