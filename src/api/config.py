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

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "bugbounty"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"

    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    RABBITMQ_VHOST: str = "/"

    LOG_LEVEL: str = "INFO"
    TOOLS_PATH_PREFIX: str = "/usr/local"
    ORCHESTRATOR_MAX_CONCURRENT: int = 5
    ORCHESTRATOR_SCAN_DELAY: float = 30.0

    # Pipeline feature flag
    USE_NODE_PIPELINE: bool = True

    # Batch processing settings
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
    AMASS_WORDLIST: str = "/usr/share/wordlists/amass/bitquark_subdomains_top100K.txt"
    AMASS_INGESTOR_BATCH_SIZE: int = 100
    AMASS_BATCH_MIN_SIZE: int = 50
    AMASS_BATCH_MAX_SIZE: int = 200
    AMASS_BATCH_TIMEOUT: int = 30

    # Subjack settings
    SUBJACK_FINGERPRINTS: str = "/usr/share/subjack/fingerprints.json"

    # PDCP (ProjectDiscovery Cloud Platform) API key
    PDCP_API_KEY: str = "05a12907-ea8e-4dfe-ac38-995bf1e7c8be"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

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
