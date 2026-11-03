import socketserver
import threading
from email import policy
from email.parser import BytesParser

import pytest

from app.core.config import settings
from app.services.email_service import send_email


class SMTPTestServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.messages = []


class SMTPTestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 localhost SMTP test server\r\n")

        while True:
            line = self.rfile.readline()

            if not line:
                break

            command = line.decode("ascii", errors="replace").strip()
            upper_command = command.upper()

            if upper_command.startswith(("EHLO", "HELO")):
                self.wfile.write(
                    b"250-localhost\r\n"
                    b"250-SIZE 1048576\r\n"
                    b"250 HELP\r\n"
                )

            elif upper_command.startswith("MAIL FROM:"):
                self.wfile.write(b"250 OK\r\n")

            elif upper_command.startswith("RCPT TO:"):
                self.wfile.write(b"250 OK\r\n")

            elif upper_command == "DATA":
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")

                message_lines = []

                while True:
                    data_line = self.rfile.readline()

                    if not data_line or data_line == b".\r\n":
                        break

                    if data_line.startswith(b".."):
                        data_line = data_line[1:]

                    message_lines.append(data_line)

                self.server.messages.append(b"".join(message_lines))
                self.wfile.write(b"250 Message accepted\r\n")

            elif upper_command == "QUIT":
                self.wfile.write(b"221 Bye\r\n")
                break

            else:
                self.wfile.write(b"250 OK\r\n")


@pytest.fixture
def local_smtp_server():
    server = SMTPTestServer(("127.0.0.1", 0), SMTPTestHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_send_email_delivers_message_to_local_smtp_server(
    local_smtp_server,
    monkeypatch,
):
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", local_smtp_server.server_address[1])
    monkeypatch.setattr(settings, "smtp_from_email", "alerts@example.test")
    monkeypatch.setattr(settings, "smtp_username", None)
    monkeypatch.setattr(settings, "smtp_password", None)
    monkeypatch.setattr(settings, "smtp_use_tls", False)
    monkeypatch.setattr(settings, "smtp_timeout_seconds", 5)

    send_email(
        to_email="user@example.test",
        subject="Uptime Monitor Alert",
        body="Your website is currently unavailable.",
    )

    assert len(local_smtp_server.messages) == 1

    message = BytesParser(policy=policy.default).parsebytes(
        local_smtp_server.messages[0]
    )

    assert message["From"] == "alerts@example.test"
    assert message["To"] == "user@example.test"
    assert message["Subject"] == "Uptime Monitor Alert"
    assert message.get_content().strip() == (
        "Your website is currently unavailable."
    )


def test_send_email_requires_smtp_host(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from_email", "alerts@example.test")

    with pytest.raises(RuntimeError, match="SMTP_HOST is not configured"):
        send_email("user@example.test", "Test", "Test body")


def test_send_email_requires_from_address(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_from_email", None)

    with pytest.raises(RuntimeError, match="SMTP_FROM_EMAIL is not configured"):
        send_email("user@example.test", "Test", "Test body")
