from typing import Literal

from pydantic import (
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Website & API Uptime Monitor"
    app_env: str = "development"
    database_url: str
    cors_origins: str = "http://localhost:5173"

    # JWT authentication
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)

    # Authentication cookies
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # SMTP email configuration
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = 10

    # Incident detection configuration
    incident_failure_threshold: int = Field(
        default=3,
        ge=1,
        le=20,
    )
    incident_recovery_threshold: int = Field(
        default=2,
        ge=1,
        le=20,
    )

    # Check-result data retention
    check_result_retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
    )
    retention_cleanup_batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator("cookie_samesite")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_cookie_security(self):
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SECURE must be true when COOKIE_SAMESITE is none."
            )

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.cors_origins.split(",")
            if item.strip()
        ]


settings = Settings()