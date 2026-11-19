"""Provider-neutral outbound email (SMTP via the standard library).

Development uses Mailpit (a local SMTP catcher, docker-compose `mailpit`); production uses any
SMTP-capable provider configured through SMTP_* settings (provider choice is decision D-18).
Header values are set through `email.message.EmailMessage`, which rejects CR/LF (no header
injection). Messages carry a stable Message-ID so repeated at-least-once deliveries can be
recognised as duplicates.
"""

import asyncio
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str
    message_id: str


class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...


def build_message(email: OutgoingEmail, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message["Date"] = formatdate(usegmt=True)
    message["Message-ID"] = email.message_id
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    return message


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host or not settings.email_from:
            raise RuntimeError("SMTP_HOST and EMAIL_FROM are required to send email")
        self._settings = settings
        self._host = settings.smtp_host
        self._sender = settings.email_from

    def _send_blocking(self, message: EmailMessage) -> None:
        s = self._settings
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if s.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(
                self._host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=context
            )
        else:
            smtp = smtplib.SMTP(self._host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        with smtp:
            if s.smtp_security == "starttls":
                smtp.starttls(context=context)
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(message)

    async def send(self, email: OutgoingEmail) -> None:
        await asyncio.to_thread(self._send_blocking, build_message(email, self._sender))


@dataclass
class MemoryEmailSender:
    """Test double: records messages instead of sending them."""

    sent: list[OutgoingEmail] = field(default_factory=list)
    fail_next: int = 0

    async def send(self, email: OutgoingEmail) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise smtplib.SMTPServerDisconnected("simulated SMTP failure")
        self.sent.append(email)
