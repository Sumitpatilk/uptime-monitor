import ipaddress
from contextlib import contextmanager
from types import SimpleNamespace

import httpx

from app.services import check_engine


class FakeClient:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.request = None
        self.stream_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    @contextmanager
    def stream(self, method, url, headers=None, extensions=None):
        self.stream_called = True

        self.request = httpx.Request(
            method,
            url,
            headers=headers,
            extensions=extensions,
        )

        response = httpx.Response(
            status_code=200,
            request=self.request,
        )

        yield response


def test_perform_http_check_uses_validated_pinned_ip(monkeypatch):
    captured = {}

    addresses = {
        ipaddress.ip_address("8.8.8.8"),
        ipaddress.ip_address("1.1.1.1"),
    }

    def fake_resolve_public_url(url):
        captured["validated_url"] = url
        return "example.com", 8443, addresses

    def fake_client_factory(**kwargs):
        client = FakeClient(**kwargs)
        captured["client"] = client
        return client

    monkeypatch.setattr(
        check_engine,
        "resolve_public_url",
        fake_resolve_public_url,
    )
    monkeypatch.setattr(
        check_engine.httpx,
        "Client",
        fake_client_factory,
    )

    monitor = SimpleNamespace(
        url="https://example.com:8443/health?check=1",
        timeout_seconds=10,
        expected_status=200,
    )

    result = check_engine.perform_http_check(monitor)

    client = captured["client"]
    request = client.request

    assert result["status"] == "up"
    assert result["status_code"] == 200
    assert result["error_code"] is None

    assert request.url.host == "1.1.1.1"
    assert request.url.port == 8443
    assert request.url.path == "/health"
    assert request.url.query == b"check=1"

    assert request.headers["Host"] == "example.com:8443"
    assert request.extensions["sni_hostname"] == "example.com"

    assert client.options["follow_redirects"] is False
    assert client.options["trust_env"] is False
    assert client.stream_called is True


def test_perform_http_check_rejects_unsafe_url(monkeypatch):
    def fake_resolve_public_url(url):
        raise ValueError("Private or reserved IP addresses are not allowed.")

    monkeypatch.setattr(
        check_engine,
        "resolve_public_url",
        fake_resolve_public_url,
    )

    monitor = SimpleNamespace(
        url="http://127.0.0.1",
        timeout_seconds=10,
        expected_status=200,
    )

    result = check_engine.perform_http_check(monitor)

    assert result["status"] == "down"
    assert result["status_code"] is None
    assert result["error_code"] == "unsafe_url"
    assert result["latency_ms"] is not None