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
    
    # Sprint V4.4: Day-level strength target mode
    day_level_strength_target_mode: str = "legacy_ratio"  # Options: "legacy_ratio", "heaviest_quality_set_perf_y", "fixed_load_first_rep_velocity", "quality_set_composite"
    
    # Strava OAuth settings
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/integrations/strava/callback"
    strava_scopes: str = "read,activity:read_all"
    app_base_url: str = "http://localhost:8000"
    
    class Config:
        env_file = ".env"


settings = Settings()
