"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "bbframework"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    @property
    def postgres_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    class Config:
        env_file = ".env"

settings = Settings()
