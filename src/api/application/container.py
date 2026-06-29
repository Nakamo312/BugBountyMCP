from dishka import make_async_container

from api.application.di import (
    ActionProvider,
    AgentProvider,
    BatchProcessorProvider,
    CLIRunnerProvider,
    CredentialProvider,
    DatabaseProvider,
    IngestorProvider,
    PipelineProvider,
    ProjectionReadModelProvider,
    ResearchProvider,
    ServiceProvider,
    UnitOfWorkProvider,
)


def create_container(context: dict):
    return make_async_container(
        DatabaseProvider(),
        UnitOfWorkProvider(),
        ActionProvider(),
        AgentProvider(),
        ProjectionReadModelProvider(),
        ResearchProvider(),
        CredentialProvider(),
        CLIRunnerProvider(),
        BatchProcessorProvider(),
        IngestorProvider(),
        ServiceProvider(),
        PipelineProvider(),
        context=context,
    )
