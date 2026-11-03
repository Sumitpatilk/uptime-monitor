
import ipaddress
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from app.services import check_engine


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def run_tls_check(tmp_path, monkeypatch, certificate_hostname):
    key_file = tmp_path / "server.key"
    cert_file = tmp_path / "server.crt"

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key_file),
            "-out",
            str(cert_file),
            "-days",
            "1",
            "-subj",
            f"/CN={certificate_hostname}",
            "-addext",
            f"subjectAltName=DNS:{certificate_hostname}",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        HealthHandler,
    )

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(
        certfile=str(cert_file),
        keyfile=str(key_file),
    )

    server.socket = server_context.wrap_socket(
        server.socket,
        server_side=True,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    client_context = ssl.create_default_context(
        cafile=str(cert_file),
    )

    real_httpx_client = httpx.Client

    def trusted_client(**kwargs):
        return real_httpx_client(
            verify=client_context,
            **kwargs,
        )

    monkeypatch.setattr(
        check_engine.httpx,
        "Client",
        trusted_client,
    )

    monkeypatch.setattr(
        check_engine,
        "resolve_public_url",
        lambda url: (
            "localhost",
            server.server_port,
            {ipaddress.ip_address("127.0.0.1")},
        ),
    )

    monitor = type(
        "Monitor",
        (),
        {
            "url": f"https://localhost:{server.server_port}/health",
            "timeout_seconds": 5,
            "expected_status": 200,
        },
    )()

    try:
        return check_engine.perform_http_check(monitor)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_https_check_accepts_matching_certificate(
    tmp_path,
    monkeypatch,
):
    result = run_tls_check(
        tmp_path,
        monkeypatch,
        certificate_hostname="localhost",
    )

    assert result["status"] == "up"
    assert result["status_code"] == 200
    assert result["error_code"] is None


def test_https_check_rejects_hostname_mismatch(
    tmp_path,
    monkeypatch,
):
    result = run_tls_check(
        tmp_path,
        monkeypatch,
        certificate_hostname="wrong.example",
    )

    assert result["status"] == "down"
    assert result["error_code"] in {
        "connection_error",
        "request_error",
    }
