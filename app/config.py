"""Application configuration."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./concurrent_training.db"
    redis_url: str = "redis://localhost:6379/0"
    debug: bool = False
    log_level: str = "INFO"
    app_env: str = "development"

    # Authentication is optional only for local development and tests.
    require_api_key: bool = False
    admin_api_key: str = "dev-api-key-change-in-production"
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    auto_create_tables: bool = True

    use_legacy_model: bool = False
    day_level_strength_target_mode: str = "heaviest_quality_set_perf_y"

    # Strava OAuth and token protection.
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/integrations/strava/callback"
    strava_scopes: str = "read,activity:read_all"
    app_base_url: str = "http://localhost:8000"
    strava_state_ttl_seconds: int = 600
    strava_token_encryption_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env.lower() == "production":
            self.require_api_key = True
            self.auto_create_tables = False
            if self.admin_api_key == "dev-api-key-change-in-production" or len(self.admin_api_key) < 24:
                raise ValueError("A strong ADMIN_API_KEY is required in production")
            if self.strava_client_id and not self.strava_token_encryption_key:
                raise ValueError("STRAVA_TOKEN_ENCRYPTION_KEY is required when Strava is enabled in production")
        return self


settings = Settings()
