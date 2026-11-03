
import socket

import pytest

from app.schemas.monitor import validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://localhost:8000/health",
        "http://example.local",
        "http://service.internal",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://172.16.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://[fc00::1]",
        "http://[fe80::1]",
    ],
)
def test_rejects_local_and_private_urls(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "file:///etc/passwd",
        "http://user:password@example.com",
    ],
)
def test_rejects_unsupported_schemes_and_credentials(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_rejects_hostname_when_dns_resolution_fails(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        raise socket.gaierror("DNS resolution failed")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    with pytest.raises(ValueError, match="Hostname could not be resolved"):
        validate_public_url("https://unresolvable.example.test")


def test_rejects_hostname_if_any_dns_result_is_private(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.1", 443),
            ),
        ]

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    with pytest.raises(ValueError, match="Private or reserved"):
        validate_public_url("https://mixed-dns.example.test")


def test_accepts_public_ipv4_address():
    assert validate_public_url("https://8.8.8.8") == "https://8.8.8.8"
