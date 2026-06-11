"""Environment-driven settings for the standalone search indexer."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    opensearch_url: str
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_verify_certs: bool = True
    opensearch_timeout_seconds: float = 30.0

    @property
    def postgres_dsn(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        host = self.postgres_host
        port = self.postgres_port
        db = quote_plus(self.postgres_db)
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def load_settings() -> Settings:
    return Settings(
        postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=os.environ["POSTGRES_DB"],
        postgres_user=os.environ["POSTGRES_USER"],
        postgres_password=os.environ["POSTGRES_PASSWORD"],
        opensearch_url=os.getenv("OPENSEARCH_URL", "http://opensearch:9200"),
        opensearch_username=os.getenv("OPENSEARCH_USERNAME") or None,
        opensearch_password=os.getenv("OPENSEARCH_PASSWORD") or None,
        opensearch_verify_certs=os.getenv("OPENSEARCH_VERIFY_CERTS", "true").lower() in {
            "1",
            "true",
            "yes",
        },
        opensearch_timeout_seconds=float(os.getenv("OPENSEARCH_TIMEOUT_SECONDS", "30")),
    )
