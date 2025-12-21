"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Optional
import os

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
    
    # Tools path prefix (for Docker - use /host prefix to access host tools)
    TOOLS_PATH_PREFIX: str = os.getenv("TOOLS_PATH_PREFIX", "")
    
    @property
    def postgres_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    def get_tool_path(self, tool_name: str) -> str:
        """
        Get full path to tool, considering TOOLS_PATH_PREFIX for Docker.
        
        Args:
            tool_name: Name of the tool (e.g., 'httpx', 'subfinder')
            
        Returns:
            Full path to tool or just tool name if prefix is empty
        """
        if self.TOOLS_PATH_PREFIX:
            # Check common tool locations
            for path in [
                f"{self.TOOLS_PATH_PREFIX}/usr/local/bin/{tool_name}",
                f"{self.TOOLS_PATH_PREFIX}/usr/bin/{tool_name}",
                f"{self.TOOLS_PATH_PREFIX}/opt/tools/{tool_name}",
            ]:
                if os.path.exists(path):
                    return path
            # Fallback: return prefixed path anyway
            return f"{self.TOOLS_PATH_PREFIX}/usr/local/bin/{tool_name}"
        return tool_name
    
    class Config:
        env_file = ".env"

settings = Settings()
