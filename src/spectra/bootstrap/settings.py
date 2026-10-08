from enum import StrEnum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from spectra.analysis.domain.tempo import MAX_BPM, MIN_BPM


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
    frame_rate_hz: float = Field(default=60.0, gt=0.0, allow_inf_nan=False)
    synthetic_bpm: float = Field(default=128.0, ge=MIN_BPM, le=MAX_BPM)
    log_level: LogLevel = LogLevel.INFO

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
