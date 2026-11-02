import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings


logger = logging.getLogger("uptime-monitor.email")


def send_email(
    to_email: str,
    subject: str,
    body: str,
) -> None:
    """
    Send an email using the configured SMTP server.
    Raises RuntimeError if SMTP configuration is missing.
    Raises SMTP/network exceptions if delivery fails.
    """

    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is not configured.")

    if not settings.smtp_from_email:
        raise RuntimeError("SMTP_FROM_EMAIL is not configured.")

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as server:

            server.ehlo()

            if settings.smtp_use_tls:
                server.starttls(context=context)
                server.ehlo()

            if settings.smtp_username and settings.smtp_password:
                server.login(
                    settings.smtp_username,
                    settings.smtp_password,
                )

            server.send_message(message)

        logger.info("Email successfully sent to %s", to_email)

    except (smtplib.SMTPException, OSError):
        logger.exception("Failed to send email to %s", to_email)
        raise
