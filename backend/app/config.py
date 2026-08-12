from functools import lru_cache
from typing import Optional

from pydantic import BaseSettings, root_validator, validator


class Settings(BaseSettings):
    api_key: Optional[str] = None
    data_encryption_key: Optional[str] = None
    browser_dsn: str = "http://browser:4444/wd/hub"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    data_dir: str = "./data"
    environment: str = "development"

    @validator("environment", pre=True)
    def normalize_environment(cls, value):
        return str(value).strip().lower()

    @validator("log_level", pre=True)
    def normalize_log_level(cls, value):
        return str(value).strip().upper()

    @root_validator
    def require_production_secrets(cls, values):
        if values.get("environment", "development").lower() == "production":
            missing = [
                name
                for name in ("api_key", "data_encryption_key")
                if not values.get(name)
            ]
            if missing:
                raise ValueError(
                    "API_KEY and DATA_ENCRYPTION_KEY are required in production"
                )
        return values

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
