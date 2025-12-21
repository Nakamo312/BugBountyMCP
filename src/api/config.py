import os
from pydantic_settings import BaseSettings

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
    TOOLS_PATH_PREFIX: str = "/host_root"
    
    @property
    def postgres_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    def get_tool_path(self, tool_name: str) -> str:
        prefix = self.TOOLS_PATH_PREFIX
        search_paths = [
            f"{prefix}/go_bin/{tool_name}",
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
    
    class Config:
        env_file = ".env"

settings = Settings()