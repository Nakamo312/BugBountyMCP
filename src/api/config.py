# api/config.py
import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = ConfigDict(
        extra='ignore',
        env_file=".env",
        env_file_encoding="utf-8"
    )

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    POSTGRES_MCP_HOST: str = "0.0.0.0"
    POSTGRES_MCP_PORT: int = 8010
    POSTGRES_MCP_TRANSPORT: str = "http"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "bugbounty"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_MCP_DSN: str | None = None

    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    RABBITMQ_VHOST: str = "/"
    RABBITMQ_PREFETCH_COUNT: int = 10

    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_USERNAME: str | None = None
    OPENSEARCH_PASSWORD: str | None = None
    OPENSEARCH_VERIFY_CERTS: bool = True
    OPENSEARCH_TIMEOUT_SECONDS: float = 10.0

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"

    # Durable event dispatch from PostgreSQL event_store to RabbitMQ.
    USE_EVENT_DISPATCHER: bool = True
    EVENT_DISPATCH_BATCH_SIZE: int = 100
    EVENT_DISPATCH_LEASE_TTL_SECONDS: int = 30
    EVENT_DISPATCH_MAX_ATTEMPTS: int = 10
    EVENT_DISPATCH_RETRY_DELAY_SECONDS: float = 5.0
    EVENT_DISPATCH_SWEEP_INTERVAL_SECONDS: float = 5.0
    EVENT_DISPATCH_NOTIFY_CHANNEL: str = "event_dispatches_changed"
    USE_AGENT_WAIT_PROCESSOR: bool = True
    AGENT_WAIT_SWEEP_INTERVAL_SECONDS: float = 5.0
    USE_AGENT_INBOX_PROCESSOR: bool = False
    AGENT_TASK_RUNTIME: str = "bounded"
    AGENT_TASK_RUNTIME_DEFAULT_MODE: str = "none"
    AGENT_TASK_RUNTIME_ALLOW_DEEP: bool = False
    AGENT_TASK_RUNTIME_REQUIRE_DEEP_CONFIRMATION: bool = True
    AGENT_TASK_RUNTIME_DEEP_ALLOWED_ACTORS: str = "human,operator,admin"
    AGENT_TASK_LANGGRAPH_CHECKPOINT_NS: str = "agent-task"
    AGENT_TASK_CONTEXT_REF_LIMIT: int = 25
    AGENT_TASK_CONTEXT_THREAD_MESSAGE_LIMIT: int = 8
    AGENT_TASK_CONTEXT_RECENT_OUTCOME_LIMIT: int = 8
    AGENT_TASK_CONTEXT_PENDING_PROPOSAL_LIMIT: int = 5
    AGENT_TASK_CONTEXT_SURFACE_SAMPLE_LIMIT: int = 8
    AGENT_PROTOCOL_INTERNAL_TOKEN: str | None = None
    AGENT_PROTOCOL_ALLOWED_ACTORS: str = "agent-worker,operator,admin"
    AGENT_PROTOCOL_ALLOW_UNAUTHENTICATED_INTERNAL: bool = False
    AGENT_INBOX_CONSUMER_ID: str = "mvp-research-inbox-worker"
    AGENT_INBOX_KEY: str = "mvp-hypothesis-builder"
    AGENT_INBOX_CLAIM_LIMIT: int = 20
    AGENT_INBOX_LEASE_SECONDS: int = 300
    AGENT_INBOX_SWEEP_INTERVAL_SECONDS: float = 2.0

    LOG_LEVEL: str = "INFO"
    TOOLS_PATH_PREFIX: str = "/usr/local"
    ORCHESTRATOR_MAX_CONCURRENT: int = 5
    MAX_ACTION_DURATION_SECONDS: float = 1800
    MAX_ACTION_TARGETS: int = 1000
    MAX_ACTION_RATE_PER_SECOND: float = 1000
    ORCHESTRATOR_SCAN_DELAY: float = 30.0
    CAMPAIGN_MAX_RUNS: int = 1000
    CAMPAIGN_MAX_TARGETS: int = 100000
    CAMPAIGN_TOKEN_CAPACITY: float = 100.0
    CAMPAIGN_TOKEN_REFILL_PER_SECOND: float = 1.0
    CAMPAIGN_QUIESCENCE_WINDOW_SECONDS: float = 30.0

    # Pipeline feature flag
    USE_NODE_PIPELINE: bool = True
    PIPELINE_CONFIG_PATH: str | None = None
    PIPELINE_SCHEDULED_EXECUTOR_POLL_SECONDS: float = 1.0
    PIPELINE_SCHEDULED_EXECUTOR_BATCH_SIZE: int = 100
    PIPELINE_SCHEDULER_ENABLED: bool = True
    PIPELINE_SCHEDULER_LEASE_TTL_SECONDS: int = 60
    PIPELINE_SCHEDULER_RUNNING_TIMEOUT_SECONDS: int = 7200
    PIPELINE_SCHEDULER_FLUSHING_TIMEOUT_SECONDS: int = 900
    PIPELINE_RETRY_REQUEUE_LIMIT_PER_NODE: int = 25
    PIPELINE_RETRY_REQUEUE_JITTER_SECONDS: float = 10.0

    # Declarative action scheduler
    USE_SCHEDULER: bool = True
    SCHEDULER_CONFIG_PATH: str | None = None
    SCHEDULER_TICK_SECONDS: float = 5.0

    # Credential secret storage composition
    # Default backend is encrypted Postgres; building the store requires
    # CREDENTIAL_MASTER_KEY so plaintext cannot become an accidental fallback.
    CREDENTIAL_SECRET_BACKEND: str = "postgres_encrypted"
    CREDENTIAL_MASTER_KEY: str | None = None
    CREDENTIAL_KEY_ID: str = "local-env-master-key"
    CREDENTIAL_ALLOW_DEV_PLAINTEXT: bool = False

    # Raw runner output artifacts
    RAW_OUTPUT_DIR: str = "data/raw_outputs"
    RAW_OUTPUT_COMPRESSION_THRESHOLD_BYTES: int = 1024 * 1024
    RAW_OUTPUT_PREVIEW_LIMIT_BYTES: int = 16 * 1024

    # Batch processing settings
    HOST_FINDING_BATCH_MIN: int = 50
    HOST_FINDING_BATCH_MAX: int = 200
    HOST_FINDING_BATCH_TIMEOUT: float = 10.0

    URL_FINDING_BATCH_MIN: int = 100
    URL_FINDING_BATCH_MAX: int = 500
    URL_FINDING_BATCH_TIMEOUT: float = 15.0

    SUBFINDER_BATCH_MIN: int = 50
    SUBFINDER_BATCH_MAX: int = 200
    SUBFINDER_BATCH_TIMEOUT: float = 10.0

    HTTPX_BATCH_MIN: int = 200
    HTTPX_BATCH_MAX: int = 500
    HTTPX_BATCH_TIMEOUT: float = 15.0

    GAU_BATCH_MIN: int = 500
    GAU_BATCH_MAX: int = 1000
    GAU_BATCH_TIMEOUT: float = 20.0

    KATANA_BATCH_MIN: int = 100
    KATANA_BATCH_MAX: int = 100
    KATANA_BATCH_TIMEOUT: float = 10.0

    DNSX_BATCH_MIN: int = 100
    DNSX_BATCH_MAX: int = 300
    DNSX_BATCH_TIMEOUT: float = 10.0

    # ASNMap batch settings
    ASNMAP_BATCH_MIN: int = 10
    ASNMAP_BATCH_MAX: int = 50
    ASNMAP_BATCH_TIMEOUT: float = 5.0

    # Naabu batch settings
    NAABU_BATCH_MIN: int = 50
    NAABU_BATCH_MAX: int = 200
    NAABU_BATCH_TIMEOUT: float = 15.0

    # ServiceFinding batch settings
    SERVICE_FINDING_BATCH_MIN: int = 50
    SERVICE_FINDING_BATCH_MAX: int = 200
    SERVICE_FINDING_BATCH_TIMEOUT: float = 15.0

    # MapCIDR batch settings
    MAPCIDR_BATCH_MIN: int = 50
    MAPCIDR_BATCH_MAX: int = 200
    MAPCIDR_BATCH_TIMEOUT: float = 10.0

    # TLSx batch settings
    TLSX_BATCH_MIN: int = 50
    TLSX_BATCH_MAX: int = 200
    TLSX_BATCH_TIMEOUT: float = 15.0

    # Ingestor settings
    HTTPX_INGESTOR_BATCH_SIZE: int = 50
    HTTPX_NEW_HOST_BATCH_SIZE: int = 50
    KATANA_INGESTOR_BATCH_SIZE: int = 50
    DNSX_INGESTOR_BATCH_SIZE: int = 100
    ASNMAP_INGESTOR_BATCH_SIZE: int = 50
    NAABU_INGESTOR_BATCH_SIZE: int = 100
    TLSX_INGESTOR_BATCH_SIZE: int = 50

    # FFUF settings
    FFUF_WORDLIST: str = "/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt"
    FFUF_RATE_LIMIT: int = 10

    # Amass settings
    AMASS_WORDLIST: str = "/usr/share/seclists/Discovery/DNS/bitquark-subdomains-top100000.txt"
    AMASS_INGESTOR_BATCH_SIZE: int = 100
    AMASS_BATCH_MIN_SIZE: int = 50
    AMASS_BATCH_MAX_SIZE: int = 200
    AMASS_BATCH_TIMEOUT: int = 30

    # Subjack settings
    SUBJACK_FINGERPRINTS: str = "/usr/share/subjack/fingerprints.json"

    # PDCP (ProjectDiscovery Cloud Platform) API key
    PDCP_API_KEY: str = ""

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def postgres_mcp_dsn(self) -> str:
        return self.POSTGRES_MCP_DSN or self.postgres_dsn

    @property
    def postgres_asyncpg_dsn(self) -> str:
        return self.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/{self.RABBITMQ_VHOST}"
        )

    def get_tool_path(self, tool_name: str) -> str:
        prefix = self.TOOLS_PATH_PREFIX
        search_paths = [
            f"{prefix}/go_bin/bin/{tool_name}",
            f"{prefix}/usr_local_bin/{tool_name}",
            f"{prefix}/usr_bin/{tool_name}",
            f"/usr/local/bin/{tool_name}",
            f"/usr/bin/{tool_name}",
        ]
        for path in search_paths:
            if os.path.exists(path):
                return path
        return tool_name

    def get_file_path(self, relative_path: str) -> str:
        if relative_path.startswith("/usr/share"):
            return relative_path
        shared_path = os.path.join("/usr/share", relative_path.lstrip("/"))
        if os.path.exists(shared_path):
            return shared_path
        return relative_path
