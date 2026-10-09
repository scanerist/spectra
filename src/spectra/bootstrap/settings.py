from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import Field, SecretStr, field_validator
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
    max_pending_analyses: int = Field(default=4, ge=1)
    max_duration_s: float = Field(default=1_800.0, gt=0.0, allow_inf_nan=False)

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRA_POSTGRES_", frozen=True)

    host: str
    port: int = Field(default=5432, ge=1, le=65_535)
    database: str = "spectra"
    user: str = "spectra"
    password: SecretStr


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRA_REDIS_", frozen=True)

    host: str
    port: int = Field(default=6379, ge=1, le=65_535)
    database: int = Field(default=0, ge=0)
    password: SecretStr | None = None


class S3Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRA_S3_", frozen=True)

    url: str
    region: str = "us-east-1"
    access_key: str
    secret_key: SecretStr
    bucket: str = Field(default="spectra", min_length=3, max_length=63)


@dataclass(frozen=True, slots=True, kw_only=True)
class HostedSettings:
    postgres: PostgresSettings
    redis: RedisSettings
    s3: S3Settings

    @classmethod
    def from_environment(cls) -> Self:
        return cls(postgres=PostgresSettings(), redis=RedisSettings(), s3=S3Settings())
