from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class GraphProjectorSettings:
    neo4j_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "neo4j"
    postgres_dsn: str = "postgresql://postgres:postgres@postgres:5432/postgres"
    worker_id: str = "graph-projector"
    batch_lock_seconds: int = 300
    batch_max_attempts: int = 3
    batch_poll_seconds: float = 1.0
    graph_fact_batch_notify_channel: str = "graph_fact_batches_changed"
    graph_projection_event_notify_channel: str = "graph_projection_events_changed"
    graph_projection_event_poll_seconds: float = 1.0
    raw_artifact_enqueue_limit: int = 100
    raw_artifact_enqueue_poll_seconds: float = 5.0
    http_observation_enqueue_limit: int = 100
    http_observation_enqueue_poll_seconds: float = 5.0
    javascript_reference_enqueue_limit: int = 100
    javascript_reference_enqueue_poll_seconds: float = 5.0
    action_experience_proposal_limit: int = 100
    action_experience_candidate_limit: int = 5
    action_experience_similarity_cutoff: float = 0.1
    action_experience_proposal_poll_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> "GraphProjectorSettings":
        return cls(
            neo4j_enabled=_env_bool("NEO4J_ENABLED", default=False),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "neo4j"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            postgres_dsn=_postgres_dsn_from_env(),
            worker_id=os.getenv("GRAPH_PROJECTOR_WORKER_ID", "graph-projector"),
            batch_lock_seconds=_env_int("GRAPH_FACT_BATCH_LOCK_SECONDS", default=300),
            batch_max_attempts=_env_int("GRAPH_FACT_BATCH_MAX_ATTEMPTS", default=3),
            batch_poll_seconds=_env_float("GRAPH_FACT_BATCH_POLL_SECONDS", default=1.0),
            graph_fact_batch_notify_channel=os.getenv("GRAPH_FACT_BATCH_NOTIFY_CHANNEL", "graph_fact_batches_changed"),
            graph_projection_event_notify_channel=os.getenv(
                "GRAPH_PROJECTION_EVENT_NOTIFY_CHANNEL",
                "graph_projection_events_changed",
            ),
            graph_projection_event_poll_seconds=_env_float("GRAPH_PROJECTION_EVENT_POLL_SECONDS", default=1.0),
            raw_artifact_enqueue_limit=_env_int("RAW_ARTIFACT_ENQUEUE_LIMIT", default=100),
            raw_artifact_enqueue_poll_seconds=_env_float("RAW_ARTIFACT_ENQUEUE_POLL_SECONDS", default=5.0),
            http_observation_enqueue_limit=_env_int("HTTP_OBSERVATION_ENQUEUE_LIMIT", default=100),
            http_observation_enqueue_poll_seconds=_env_float("HTTP_OBSERVATION_ENQUEUE_POLL_SECONDS", default=5.0),
            javascript_reference_enqueue_limit=_env_int("JAVASCRIPT_REFERENCE_ENQUEUE_LIMIT", default=100),
            javascript_reference_enqueue_poll_seconds=_env_float("JAVASCRIPT_REFERENCE_ENQUEUE_POLL_SECONDS", default=5.0),
            action_experience_proposal_limit=_env_int("ACTION_EXPERIENCE_PROPOSAL_LIMIT", default=100),
            action_experience_candidate_limit=_env_int("ACTION_EXPERIENCE_CANDIDATE_LIMIT", default=5),
            action_experience_similarity_cutoff=_env_float("ACTION_EXPERIENCE_SIMILARITY_CUTOFF", default=0.1),
            action_experience_proposal_poll_seconds=_env_float("ACTION_EXPERIENCE_PROPOSAL_POLL_SECONDS", default=5.0),
        )


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw.strip())


def _env_float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw.strip())


def _postgres_dsn_from_env() -> str:
    explicit = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "postgres")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(database)}"
