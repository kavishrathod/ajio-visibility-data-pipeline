"""Alert delivery: a local file sink (default) or SMTP. Credentials come only from the environment."""
from __future__ import annotations

import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class Mailer:
    """Send an alert. ``send`` returns True only when the primary channel accepted the message.

    ALERT_SINK=file (default): write ``data/outbox/*.eml`` - works with no mail server.
    ALERT_SINK=smtp: deliver via SMTP_HOST/SMTP_PORT (e.g. Mailpit on localhost:1025)
    and also keep an .eml copy for audit. SMTP failures are logged and reported as
    False; the caller keeps the incident so delivery is retried at the next check.
    """

    def __init__(self, root: Path, sink: str | None = None) -> None:
        self.root = Path(root)
        self.sink = (sink or os.getenv("ALERT_SINK", "file")).strip().lower()
        self.outbox = Path(os.getenv("ALERT_OUTBOX_DIR", "data/outbox"))
        if not self.outbox.is_absolute():
            self.outbox = self.root / self.outbox

    def _message(self, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = os.getenv("ALERT_FROM", "alerts@example.local")
        message["To"] = os.getenv("ALERT_TO", "you@example.local")
        message["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        message.set_content(body)
        return message

    def _write_file(self, message: EmailMessage) -> Path:
        self.outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        slug = re.sub(r"[^a-z0-9]+", "-", str(message["Subject"]).lower()).strip("-")[:60]
        path = self.outbox / f"{stamp}_{slug}.eml"
        path.write_bytes(bytes(message))
        return path

    def send(self, subject: str, body: str) -> bool:
        message = self._message(subject, body)
        try:
            path = self._write_file(message)
        except OSError as exc:
            logger.warning("Could not write alert file (%s): %s", exc, subject)
            path = None
        if self.sink != "smtp":
            return path is not None
        host = os.getenv("SMTP_HOST", "")
        port = int(os.getenv("SMTP_PORT", "1025"))
        if not host:
            logger.warning("ALERT_SINK=smtp but SMTP_HOST is empty; alert only saved as file: %s", subject)
            return False
        try:
            with smtplib.SMTP(host, port, timeout=4) as smtp:
                if os.getenv("SMTP_STARTTLS", "false").lower() in {"1", "true", "yes"}:
                    smtp.starttls()
                username = os.getenv("SMTP_USER", "")
                if username:
                    smtp.login(username, os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(message)
            return True
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("Email delivery failed (%s). Incident stays open and will be retried. Subject: %s", exc, subject)
            return False
