"""Application configuration"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment"""
    database_url: str = "sqlite:///./concurrent_training.db"
    redis_url: str = "redis://localhost:6379/0"
    debug: bool = False
    log_level: str = "INFO"
    admin_api_key: str = "dev-api-key-change-in-production"
    
    # Sprint A: Feature flag for legacy model
    use_legacy_model: bool = False  # USE_LEGACY_MODEL env var
    
    class Config:
        env_file = ".env"


settings = Settings()
