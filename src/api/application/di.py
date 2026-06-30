# api/application/di.py
"""Dependency injection compatibility façade.

Provider wiring lives under api.infrastructure.providers because it constructs
infrastructure adapters for application ports. This file keeps legacy imports
stable for old application-level DI imports.
"""

from api.infrastructure.providers.action_runtime import ActionRuntimeProvider
from api.infrastructure.providers.agent_runtime import AgentRuntimeProvider
from api.infrastructure.providers.batch_processors import BatchProcessorProvider as _BatchProcessorProvider
from api.infrastructure.providers.credentials import CredentialProvider as _CredentialProvider
from api.infrastructure.providers.database import DatabaseProvider as _DatabaseProvider
from api.infrastructure.providers.database import UnitOfWorkProvider as _UnitOfWorkProvider
from api.infrastructure.providers.ingestors import IngestorProvider as _IngestorProvider
from api.infrastructure.providers.pipeline import PipelineProvider as _PipelineProvider
from api.infrastructure.providers.read_models import ReadModelProvider
from api.infrastructure.providers.research_runtime import ResearchRuntimeProvider
from api.infrastructure.providers.runners import CLIRunnerProvider as _CLIRunnerProvider
from api.infrastructure.providers.services import ServiceProvider as _ServiceProvider


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
    """Deprecated aggregate provider kept only for old imports."""


class CredentialProvider(_CredentialProvider):
    """Compatibility alias for api.infrastructure.providers.credentials.

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
