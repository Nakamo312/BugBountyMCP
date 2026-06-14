from __future__ import annotations

import argparse

from .applicator import GraphFactBatchApplicator, GraphFactBatchNotificationWaiter
from .batch_store import GraphFactBatchStore, connect_postgres
from .neo4j_driver import create_neo4j_driver
from .ontology import default_graph_ontology
from .producers.raw_artifacts import RawArtifactEnqueueLoopResult, RawArtifactGraphFactEnqueuer, RawArtifactGraphFactProducer
from .settings import GraphProjectorSettings
from .writer import GraphFactWriter, GraphOntologyRegistry


def main() -> int:
    parser = argparse.ArgumentParser(prog="graph-projector")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-config", help="Validate graph projector settings without projecting data.")
    subparsers.add_parser("apply-one", help="Claim and apply one pending GraphFactBatch to Neo4j.")
    apply_loop = subparsers.add_parser("apply-loop", help="Continuously claim and apply pending GraphFactBatch rows.")
    apply_loop.add_argument("--max-batches", type=int, default=None)
    apply_loop.add_argument("--idle-exit-after", type=int, default=None)
    apply_loop.add_argument("--poll-seconds", type=float, default=None)
    enqueue_raw_artifacts = subparsers.add_parser("enqueue-raw-artifacts", help="Enqueue GraphFactBatch rows from raw_artifacts metadata.")
    enqueue_raw_artifacts.add_argument("--limit", type=int, default=None)
    enqueue_raw_artifacts.add_argument("--program-id", default=None)
    enqueue_raw_artifacts_loop = subparsers.add_parser("enqueue-raw-artifacts-loop", help="Continuously enqueue GraphFactBatch rows from raw_artifacts metadata.")
    enqueue_raw_artifacts_loop.add_argument("--limit", type=int, default=None)
    enqueue_raw_artifacts_loop.add_argument("--program-id", default=None)
    enqueue_raw_artifacts_loop.add_argument("--max-iterations", type=int, default=None)
    enqueue_raw_artifacts_loop.add_argument("--idle-exit-after", type=int, default=None)
    enqueue_raw_artifacts_loop.add_argument("--poll-seconds", type=float, default=None)
    args = parser.parse_args()

    if args.command == "check-config":
        settings = GraphProjectorSettings.from_env()
        print(
            "graph-projector config ok: "
            f"enabled={settings.neo4j_enabled} uri={settings.neo4j_uri} database={settings.neo4j_database}"
        )
        return 0

    if args.command == "apply-one":
        applicator = _build_applicator(GraphProjectorSettings.from_env())
        result = applicator.apply_one()
        print(f"graph-projector apply-one: status={result.status} batch_id={result.batch_id}")
        return 0 if result.status in {"applied", "empty"} else 1

    if args.command == "apply-loop":
        settings = GraphProjectorSettings.from_env()
        applicator = _build_applicator(settings)
        result = applicator.apply_loop(
            max_batches=args.max_batches,
            idle_exit_after=args.idle_exit_after,
            poll_seconds=settings.batch_poll_seconds if args.poll_seconds is None else args.poll_seconds,
            wait_for_notification=_build_graphfact_batch_notification_waiter(settings).wait,
        )
        print(
            "graph-projector apply-loop: "
            f"applied={result.applied} failed={result.failed} dead={result.dead} "
            f"empty={result.empty} iterations={result.iterations} last_status={result.last_status}"
        )
        return 0 if result.dead == 0 else 1

    if args.command == "enqueue-raw-artifacts":
        settings = GraphProjectorSettings.from_env()
        enqueuer = _build_raw_artifact_enqueuer(settings)
        limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
        result = enqueuer.enqueue_pending(limit=limit, program_id=args.program_id)
        print(
            "graph-projector enqueue-raw-artifacts: "
            f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped}"
        )
        return 0

    if args.command == "enqueue-raw-artifacts-loop":
        settings = GraphProjectorSettings.from_env()
        enqueuer = _build_raw_artifact_enqueuer(settings)
        limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
        poll_seconds = settings.raw_artifact_enqueue_poll_seconds if args.poll_seconds is None else args.poll_seconds
        result = RawArtifactEnqueueLoopResult.run(
            enqueuer,
            limit=limit,
            program_id=args.program_id,
            max_iterations=args.max_iterations,
            idle_exit_after=args.idle_exit_after,
            poll_seconds=poll_seconds,
        )
        print(
            "graph-projector enqueue-raw-artifacts-loop: "
            f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped} "
            f"empty={result.empty} iterations={result.iterations}"
        )
        return 0

    return 2


def _build_raw_artifact_enqueuer(settings: GraphProjectorSettings) -> RawArtifactGraphFactEnqueuer:
    connection = connect_postgres(settings.postgres_dsn)
    store = GraphFactBatchStore(connection)
    producer = RawArtifactGraphFactProducer()
    return RawArtifactGraphFactEnqueuer(
        connection=connection,
        store=store,
        producer=producer,
        worker_id=settings.worker_id,
        lock_seconds=settings.batch_lock_seconds,
        max_attempts=settings.batch_max_attempts,
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
    return GraphFactBatchApplicator(
        store=store,
        neo4j_driver=driver,
        writer=writer,
        neo4j_database=settings.neo4j_database,
        worker_id=settings.worker_id,
        lock_seconds=settings.batch_lock_seconds,
        max_attempts=settings.batch_max_attempts,
    )


raise SystemExit(main())
