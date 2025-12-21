"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "bbframework"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    
    REDIS_URL: str = "redis://localhost:6379/0"
    
    LOG_LEVEL: str = "INFO"

    TOOLS_PATH_PREFIX: str = os.getenv("TOOLS_PATH_PREFIX", "")
    
    @property
    def postgres_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    def get_tool_path(self, tool_name: str) -> str:
        go_path = f"/home/v1k70r/go/bin/{tool_name}"
        if os.path.exists(go_path):
            return go_path
        return tool_name 
    class Config:
        env_file = ".env"

settings = Settings()
