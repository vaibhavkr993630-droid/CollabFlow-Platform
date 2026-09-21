import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


def send_email(*, to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    """
    Blocking (smtplib, not async) — deliberately: this is only ever called from a
    Celery task, which already runs on its own worker thread/process outside the
    API's event loop, so there's no event loop to block. In local dev, `smtp_host`
    points at the MailDev container (docker-compose.yml) — no real credentials
    needed, and sent mail is viewable at http://localhost:1080.
    """
    message = EmailMessage()
    message.set_content(body)
    if html_body is not None:
        # multipart/alternative: clients that render HTML use it, the rest fall back to `body`.
        message.add_alternative(html_body, subtype="html")
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.send_message(message)
