"""Pluggable mail transport.

`console` prints messages to stdout (dev); `smtp` sends through an SMTP server
(dev target: Mailpit on port 1025). The production provider is chosen later
(decision 13); it only has to implement `MailTransport.send`.
"""

from __future__ import annotations

import smtplib
import sys
import threading
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from blackkite.config import Settings, get_settings


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str


class MailTransport(Protocol):
    def send(self, mail: Mail) -> None: ...


class ConsoleTransport:
    def __init__(self, sender: str) -> None:
        self.sender = sender
        self._lock = threading.Lock()

    def send(self, mail: Mail) -> None:
        with self._lock:
            print(
                f"--- mail (console transport) ---\nFrom: {self.sender}\nTo: {mail.to}\n"
                f"Subject: {mail.subject}\n\n{mail.text}\n--- end mail ---",
                file=sys.stdout,
                flush=True,
            )


class SmtpTransport:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.mail_from
        msg["To"] = mail.to
        msg["Subject"] = mail.subject
        msg.set_content(mail.text)
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
            if self.s.smtp_starttls:
                smtp.starttls()
            if self.s.smtp_username and self.s.smtp_password:
                smtp.login(self.s.smtp_username, self.s.smtp_password.get_secret_value())
            smtp.send_message(msg)


class MemoryTransport:
    """Keeps messages in a list. For tests."""

    def __init__(self) -> None:
        self.outbox: list[Mail] = []

    def send(self, mail: Mail) -> None:
        self.outbox.append(mail)


def make_transport(settings: Settings) -> MailTransport:
    if settings.mail_transport == "smtp":
        return SmtpTransport(settings)
    return ConsoleTransport(settings.mail_from)


_transport: MailTransport | None = None


def get_mail_transport() -> MailTransport:
    """FastAPI dependency; tests override it with a MemoryTransport."""
    global _transport
    if _transport is None:
        _transport = make_transport(get_settings())
    return _transport
