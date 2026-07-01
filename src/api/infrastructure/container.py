from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dishka import make_async_container

from api.infrastructure.providers.action_runtime import ActionRuntimeProvider
from api.infrastructure.providers.agent_runtime import AgentRuntimeProvider
from api.infrastructure.providers.batch_processors import BatchProcessorProvider
from api.infrastructure.providers.credentials import CredentialProvider
from api.infrastructure.providers.database import DatabaseProvider, UnitOfWorkProvider
from api.infrastructure.providers.ingestors import IngestorProvider
from api.infrastructure.providers.pipeline import PipelineProvider
from api.infrastructure.providers.read_models import ReadModelProvider
from api.infrastructure.providers.research_runtime import ResearchRuntimeProvider
from api.infrastructure.providers.runners import CLIRunnerProvider
from api.infrastructure.providers.services import ServiceProvider


def create_container(context: Mapping[Any, Any]):
    return make_async_container(
        DatabaseProvider(),
        UnitOfWorkProvider(),
        ActionRuntimeProvider(),
        AgentRuntimeProvider(),
        ReadModelProvider(),
        ResearchRuntimeProvider(),
        CredentialProvider(),
        CLIRunnerProvider(),
        BatchProcessorProvider(),
        IngestorProvider(),
        ServiceProvider(),
        PipelineProvider(),
        context=dict(context),
    )
