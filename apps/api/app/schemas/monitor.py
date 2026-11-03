
import ipaddress
import socket
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def resolve_public_url(
    value: str,
) -> tuple[str, int, set[ipaddress.IPv4Address | ipaddress.IPv6Address]]:
    try:
        parsed = urlsplit(value)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS URLs are allowed.")

        if not parsed.hostname:
            raise ValueError("A valid hostname is required.")

        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not allowed.")

        host = parsed.hostname.lower().rstrip(".")

        if host == "localhost" or host.endswith(
            (".localhost", ".local", ".internal")
        ):
            raise ValueError("Local and internal hostnames are not allowed.")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            records = socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
            addresses = {
                ipaddress.ip_address(record[4][0].split("%")[0])
                for record in records
            }

        if not addresses:
            raise ValueError("Hostname did not resolve.")

        if any(not address.is_global for address in addresses):
            raise ValueError(
                "Private or reserved IP addresses are not allowed."
            )

        return host, port, addresses

    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    except OSError as exc:
        raise ValueError("Hostname could not be resolved.") from exc


def validate_public_url(value: str) -> str:
    resolve_public_url(value)
    return value

class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    url: str = Field(min_length=8, max_length=2048)
    interval_seconds: int = Field(default=60, ge=30, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Monitor name cannot be empty.")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_public_url(value.strip())


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Monitor name cannot be empty.")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_public_url(value.strip())


class MonitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    url: str
    interval_seconds: int
    timeout_seconds: int
    expected_status: int
    enabled: bool
    created_at: datetime

