from dishka import AsyncContainer, Provider, Scope, from_context, provide

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.action_outcomes import ActionOutcomeRecorder
from api.application.ports.artifacts import RawArtifactMetadataWriter, RawOutputCapturePort
from api.application.ports.orchestration import PipelineRunStatePort
from api.application.ports.scope import ScopeFilterPort
from api.application.pipeline.context_factory import PipelineContextFactory
from api.application.pipeline.registry import NodeRegistry
from api.config import Settings
from api.infrastructure.artifacts.raw_artifact_repository import RawArtifactRepository
from api.infrastructure.artifacts.raw_output_store import FileRawOutputStore
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.queue_config import QueueConfig
from api.infrastructure.scope.program_scope_filter import ProgramScopeFilter


class PipelineProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_raw_output_capture_port(self, settings: Settings) -> RawOutputCapturePort:
        return FileRawOutputStore(
            settings.RAW_OUTPUT_DIR,
            compression_threshold_bytes=settings.RAW_OUTPUT_COMPRESSION_THRESHOLD_BYTES,
            preview_limit_bytes=settings.RAW_OUTPUT_PREVIEW_LIMIT_BYTES,
        )

    @provide(scope=Scope.APP)
    def get_raw_artifact_metadata_writer(
        self,
        session_factory: async_sessionmaker,
    ) -> RawArtifactMetadataWriter:
        return RawArtifactRepository(session_factory)


    @provide(scope=Scope.APP)
    def get_scope_filter_port(
        self,
        session_factory: async_sessionmaker,
    ) -> ScopeFilterPort:
        return ProgramScopeFilter(session_factory)

    @provide(scope=Scope.APP)
    def get_pipeline_context_factory(
        self,
        raw_outputs: RawOutputCapturePort,
        raw_artifact_metadata: RawArtifactMetadataWriter,
        run_states: PipelineRunStatePort,
        action_outcomes: ActionOutcomeRecorder,
        scope_filter: ScopeFilterPort,
    ) -> PipelineContextFactory:
        return PipelineContextFactory(
            raw_outputs=raw_outputs,
            raw_artifact_metadata=raw_artifact_metadata,
            run_states=run_states,
            action_outcomes=action_outcomes,
            scope_filter=scope_filter,
        )

    @provide(scope=Scope.APP)
    def get_node_registry(
        self,
        bus: EventBus,
        settings: Settings,
        container: AsyncContainer,
        context_factory: PipelineContextFactory,
    ) -> NodeRegistry:
        return NodeRegistry(
            bus,
            settings,
            container,
            context_factory=context_factory,
            subscription_queues=QueueConfig.get_all_queues(),
        )
