# api/config.py
import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_HOST: str
    API_PORT: int

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: str
    RABBITMQ_VHOST: str

    LOG_LEVEL: str
    TOOLS_PATH_PREFIX: str

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
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
            f"{prefix}/usr_bin/bin/{tool_name}",
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

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()
