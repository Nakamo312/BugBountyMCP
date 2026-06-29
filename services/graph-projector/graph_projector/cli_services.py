from __future__ import annotations

from .action_experience_proposals import (
    ActionExperienceProposalStore,
    ActionExperienceProposalWorker,
)
from .applicator import GraphFactBatchApplicator, GraphFactBatchNotificationWaiter
from .batch_store import GraphFactBatchStore, connect_postgres
from .cli_enqueuer_factory import GraphFactEnqueuerFactory
from .neo4j_driver import create_neo4j_driver
from .ontology import default_graph_ontology
from .producers.action_outcomes import ActionOutcomeGraphFactEnqueuer, ActionOutcomeGraphFactProducer
from .producers.http_observations import HttpObservationGraphFactEnqueuer, HttpObservationGraphFactProducer
from .producers.javascript_references import JavaScriptReferenceGraphFactEnqueuer, JavaScriptReferenceGraphFactProducer
from .producers.raw_artifacts import RawArtifactGraphFactEnqueuer, RawArtifactGraphFactProducer
from .projection_events import GraphProjectionEventNotificationWaiter, GraphProjectionEventWorker
from .rebuild import GraphRebuildService
from .retry import GraphProjectorRetryService
from .settings import GraphProjectorSettings
from .surface_component_report import SurfaceComponentReportReader
from .surface_component_materialization import SurfaceComponentAnalysisStore
from .surface_component_analysis_events import (
    SearchProjectionEventPublisher,
    SurfaceComponentAnalysisEventStore,
    SurfaceComponentAnalysisEventWorker,
    enqueue_surface_analysis_events_from_batch,
)
from .diagnostics import GraphProjectorDiagnosticsReader
from .health import GraphProjectorHealthChecker
from .status import GraphProjectorStatusReader
from .writer import GraphFactWriter, GraphOntologyRegistry


def _build_status_reader(settings: GraphProjectorSettings) -> GraphProjectorStatusReader:
    return GraphProjectorStatusReader(connect_postgres(settings.postgres_dsn))


def _build_retry_service(settings: GraphProjectorSettings) -> GraphProjectorRetryService:
    return GraphProjectorRetryService(connect_postgres(settings.postgres_dsn))


def _build_health_checker(settings: GraphProjectorSettings) -> GraphProjectorHealthChecker:
    return GraphProjectorHealthChecker(_build_status_reader(settings))


def _build_diagnostics_reader(settings: GraphProjectorSettings) -> GraphProjectorDiagnosticsReader:
    return GraphProjectorDiagnosticsReader(connect_postgres(settings.postgres_dsn))


def _enqueuer_factory(settings: GraphProjectorSettings) -> GraphFactEnqueuerFactory:
    return GraphFactEnqueuerFactory(settings)


def _build_http_observation_enqueuer(settings: GraphProjectorSettings) -> HttpObservationGraphFactEnqueuer:
    return _enqueuer_factory(settings).build(
        producer_factory=HttpObservationGraphFactProducer,
        enqueuer_factory=HttpObservationGraphFactEnqueuer,
    )


def _build_javascript_reference_enqueuer(settings: GraphProjectorSettings) -> JavaScriptReferenceGraphFactEnqueuer:
    return _enqueuer_factory(settings).build(
        producer_factory=JavaScriptReferenceGraphFactProducer,
        enqueuer_factory=JavaScriptReferenceGraphFactEnqueuer,
    )


def _build_action_outcome_enqueuer(settings: GraphProjectorSettings) -> ActionOutcomeGraphFactEnqueuer:
    return _enqueuer_factory(settings).build(
        producer_factory=ActionOutcomeGraphFactProducer,
        enqueuer_factory=ActionOutcomeGraphFactEnqueuer,
    )


def _build_raw_artifact_enqueuer(settings: GraphProjectorSettings) -> RawArtifactGraphFactEnqueuer:
    return _enqueuer_factory(settings).build(
        producer_factory=RawArtifactGraphFactProducer,
        enqueuer_factory=RawArtifactGraphFactEnqueuer,
    )


def _build_rebuild_service(settings: GraphProjectorSettings) -> GraphRebuildService:
    connection = connect_postgres(settings.postgres_dsn)
    store = GraphFactBatchStore(connection)
    return GraphRebuildService(connection=connection, store=store)


def _build_projection_event_worker(settings: GraphProjectorSettings) -> GraphProjectionEventWorker:
    return GraphProjectionEventWorker(
        raw_artifact_enqueuer=_build_raw_artifact_enqueuer(settings),
        http_observation_enqueuer=_build_http_observation_enqueuer(settings),
        javascript_reference_enqueuer=_build_javascript_reference_enqueuer(settings),
        action_outcome_enqueuer=_build_action_outcome_enqueuer(settings),
    )


def _build_surface_component_report_reader(settings: GraphProjectorSettings) -> SurfaceComponentReportReader:
    driver = create_neo4j_driver(settings)
    if driver is None:
        raise RuntimeError("NEO4J_ENABLED must be true to read surface component analytics.")
    return SurfaceComponentReportReader(
        driver,
        neo4j_database=settings.neo4j_database,
    )


def _build_surface_component_analysis_store(settings: GraphProjectorSettings) -> SurfaceComponentAnalysisStore:
    return SurfaceComponentAnalysisStore(connect_postgres(settings.postgres_dsn))


def _build_action_experience_proposal_worker(
    settings: GraphProjectorSettings,
    *,
    candidate_limit: int | None = None,
    similarity_cutoff: float | None = None,
) -> ActionExperienceProposalWorker:
    driver = create_neo4j_driver(settings)
    if driver is None:
        raise RuntimeError("NEO4J_ENABLED must be true to produce action experience proposals.")
    connection = connect_postgres(settings.postgres_dsn)
    store = ActionExperienceProposalStore(connection, produced_by=settings.worker_id)
    return ActionExperienceProposalWorker(
        store=store,
        neo4j_driver=driver,
        neo4j_database=settings.neo4j_database,
        candidate_limit=settings.action_experience_candidate_limit if candidate_limit is None else candidate_limit,
        similarity_cutoff=(
            settings.action_experience_similarity_cutoff
            if similarity_cutoff is None
            else similarity_cutoff
        ),
    )


def _build_surface_component_analysis_event_worker(settings: GraphProjectorSettings) -> SurfaceComponentAnalysisEventWorker:
    connection = connect_postgres(settings.postgres_dsn)
    return SurfaceComponentAnalysisEventWorker(
        event_store=SurfaceComponentAnalysisEventStore(connection),
        analysis_store=SurfaceComponentAnalysisStore(connection),
        report_reader=_build_surface_component_report_reader(settings),
        worker_id=settings.worker_id,
        lock_seconds=settings.batch_lock_seconds,
        max_attempts=settings.batch_max_attempts,
        search_event_publisher=SearchProjectionEventPublisher(connection),
    )


def _build_projection_event_notification_waiter(settings: GraphProjectorSettings) -> GraphProjectionEventNotificationWaiter:
    connection = connect_postgres(settings.postgres_dsn)
    return GraphProjectionEventNotificationWaiter(
        connection,
        channel=settings.graph_projection_event_notify_channel,
    )


def _build_graphfact_batch_notification_waiter(settings: GraphProjectorSettings) -> GraphFactBatchNotificationWaiter:
    connection = connect_postgres(settings.postgres_dsn)
    return GraphFactBatchNotificationWaiter(
        connection,
        channel=settings.graph_fact_batch_notify_channel,
    )


def _build_applicator(settings: GraphProjectorSettings) -> GraphFactBatchApplicator:
    driver = create_neo4j_driver(settings)
    if driver is None:
        raise RuntimeError("NEO4J_ENABLED must be true to apply GraphFactBatch rows.")

    connection = connect_postgres(settings.postgres_dsn)
    store = GraphFactBatchStore(connection)
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    surface_event_store = SurfaceComponentAnalysisEventStore(connection)
    return GraphFactBatchApplicator(
        store=store,
        neo4j_driver=driver,
        writer=writer,
        neo4j_database=settings.neo4j_database,
        worker_id=settings.worker_id,
        lock_seconds=settings.batch_lock_seconds,
        max_attempts=settings.batch_max_attempts,
        after_apply=lambda batch: enqueue_surface_analysis_events_from_batch(
            surface_event_store,
            batch=batch,
            settings_json={
                "limit": 10,
                "candidate_limit": settings.action_experience_candidate_limit,
                "component_limit": 10,
                "similarity_cutoff": settings.action_experience_similarity_cutoff,
                "include_action_candidates": True,
            },
        ),
    )
