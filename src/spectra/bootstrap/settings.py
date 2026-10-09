from enum import StrEnum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRA_", frozen=True)

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65_535)
    log_level: LogLevel = LogLevel.INFO
    max_upload_bytes: int = Field(default=256 * 1024 * 1024, ge=1)
    max_tracks: int = Field(default=8, ge=1)

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
