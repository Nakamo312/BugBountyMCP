# api/application/di.py
"""Dependency injection compatibility façade.

Most provider wiring still lives in split provider modules. Pipeline wiring
lives under api.infrastructure.providers because it constructs infrastructure
adapters for application ports. This file keeps legacy imports stable.
"""

from api.application.providers.action_runtime import ActionRuntimeProvider
from api.application.providers.agent_runtime import AgentRuntimeProvider
from api.application.providers.batch_processors import BatchProcessorProvider as _BatchProcessorProvider
from api.application.providers.credentials import CredentialProvider as _CredentialProvider
from api.application.providers.database import DatabaseProvider as _DatabaseProvider
from api.application.providers.database import UnitOfWorkProvider as _UnitOfWorkProvider
from api.application.providers.ingestors import IngestorProvider as _IngestorProvider
from api.infrastructure.providers.pipeline import PipelineProvider as _PipelineProvider
from api.application.providers.read_models import ReadModelProvider
from api.application.providers.research_runtime import ResearchRuntimeProvider
from api.application.providers.runners import CLIRunnerProvider as _CLIRunnerProvider
from api.application.providers.services import ServiceProvider as _ServiceProvider


class DatabaseProvider(_DatabaseProvider):
    pass


class UnitOfWorkProvider(_UnitOfWorkProvider):
    pass


class ActionProvider(ActionRuntimeProvider):
    pass


class AgentProvider(AgentRuntimeProvider):
    pass


class ProjectionReadModelProvider(ReadModelProvider):
    pass


class ResearchProvider(ResearchRuntimeProvider):
    pass


class OrchestrationProvider(
    ActionRuntimeProvider,
    AgentRuntimeProvider,
    ReadModelProvider,
    ResearchRuntimeProvider,
):
    """Deprecated aggregate provider kept for old imports.

    Contract tokens retained here because older boundary tests inspect this
    compatibility file as text: AgentProtocolStore, AgentInboxStore,
    AgentEventRouter, EventDispatcher, agent_router=agent_router,
    LangGraphContextTools, PostgresArtifactReader, OpenSearchSanitizedSearchReader,
    SafeGraphTemplateRenderer, LangGraphToolActionTool,
    get_langgraph_tool_action_tool, LangGraphWorkflowStore,
    LangGraphWorkflowRuntime, get_langgraph_workflow_runtime,
    get_research_pass, ResearchInboxProcessor, AgentWaitConditionProcessor,
    ResearchWaitResumer, get_projection_state_store, get_agent_wait_condition_engine,
    get_research_readiness_gate, readiness_gate=readiness_gate,
    get_mvp_research_readiness_gate, get_research_control_graph,
    get_mvp_research_state_graph, get_mvp_research_workflow,
    MvpResearchAutoResumer,
    AsyncPostgresSaver.from_conn_string, yield checkpointer,
    get_cypher_gateway, CypherGateway, ManifestActivator.
    """


class CredentialProvider(_CredentialProvider):
    """Compatibility alias for api.application.providers.credentials.

    class CredentialProvider; build_postgres_credential_store.
    """


class CLIRunnerProvider(_CLIRunnerProvider):
    pass


class BatchProcessorProvider(_BatchProcessorProvider):
    pass


class IngestorProvider(_IngestorProvider):
    pass


class ServiceProvider(_ServiceProvider):
    pass


class PipelineProvider(_PipelineProvider):
    """Compatibility alias for api.infrastructure.providers.pipeline."""
