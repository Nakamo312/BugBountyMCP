import os

from dishka import Provider, Scope, from_context, provide

from api.config import Settings
from api.application.ports.runners import ToolRunnerFactoryPort
from api.application.ports.orchestration import EventDispatchStorePort, EventRecorderPort
from api.infrastructure.agent_coordination import AgentEventRouter
from api.infrastructure.events.dispatcher import EventDispatcher
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.runners.cli_tool_factory import CliToolRunnerFactory
from api.infrastructure.runners.playwright_cli import PlaywrightCliRunner
from api.infrastructure.runners.subjack_cli import SubjackCliRunner


class CLIRunnerProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_cli_tool_runner_factory(self, settings: Settings) -> CliToolRunnerFactory:
        return CliToolRunnerFactory(settings)

    @provide(scope=Scope.APP, provides=ToolRunnerFactoryPort)
    def get_tool_runner_factory_port(
        self,
        cli_tool_runner_factory: CliToolRunnerFactory,
    ) -> ToolRunnerFactoryPort:
        return cli_tool_runner_factory

    @provide(scope=Scope.APP)
    def get_subjack_runner(self, settings: Settings) -> SubjackCliRunner:
        fingerprints = settings.SUBJACK_FINGERPRINTS if os.path.exists(settings.SUBJACK_FINGERPRINTS) else None
        return SubjackCliRunner(
            subjack_path=settings.get_tool_path("subjack"),
            fingerprints_path=fingerprints,
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_playwright_runner(self, settings: Settings) -> PlaywrightCliRunner:
        return PlaywrightCliRunner(timeout=600)

    @provide(scope=Scope.APP)
    def get_event_bus(
        self,
        settings: Settings,
        event_recorder: EventRecorderPort,
    ) -> EventBus:
        return EventBus(settings, event_recorder=event_recorder)

    @provide(scope=Scope.APP)
    def get_event_dispatcher(
        self,
        settings: Settings,
        dispatch_store: EventDispatchStorePort,
        event_bus: EventBus,
        agent_router: AgentEventRouter,
    ) -> EventDispatcher:
        return EventDispatcher(
            store=dispatch_store,
            event_bus=event_bus,
            agent_router=agent_router,
            batch_size=settings.EVENT_DISPATCH_BATCH_SIZE,
            lease_ttl_seconds=settings.EVENT_DISPATCH_LEASE_TTL_SECONDS,
            max_attempts=settings.EVENT_DISPATCH_MAX_ATTEMPTS,
            retry_delay_seconds=settings.EVENT_DISPATCH_RETRY_DELAY_SECONDS,
            sweep_interval_seconds=settings.EVENT_DISPATCH_SWEEP_INTERVAL_SECONDS,
            notify_channel=settings.EVENT_DISPATCH_NOTIFY_CHANNEL,
            listen_dsn=settings.postgres_asyncpg_dsn,
        )
