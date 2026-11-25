"""Pluggable mail transport.

`console` prints messages to stdout (dev); `smtp` sends through an SMTP server
(dev target: Mailpit on port 1025); `resend` posts to Resend's HTTP API, the
production provider (decision 45, delivery/resend.py), and refuses to send
while BK_MAIL_ALLOW_REAL_SEND is false. A transport only has to implement
`MailTransport.send`.

A `Mail` is plain text, optionally with an HTML alternative and inline images
the HTML refers to as ``cid:<content id>`` (the digest's kite logo is
``cid:kite-logo``). `build_message` turns it into the MIME structure every
transport sends::

    multipart/alternative
      text/plain
      multipart/related
        text/html
        image/png  (Content-ID: <kite-logo>, inline)
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
class InlineImage:
    """An image the HTML part shows through ``cid:{cid}``."""

    cid: str
    data: bytes
    filename: str
    subtype: str = "png"


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str | None = None
    inline: tuple[InlineImage, ...] = ()
    # Extra headers, e.g. List-Unsubscribe (delivery/unsubscribe.py).
    headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for name, value in self.headers:
            if any(c in name + value for c in "\r\n") or not name.strip():
                raise ValueError(f"invalid mail header {name!r}")


def build_message(mail: Mail, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    for name, value in mail.headers:
        msg[name] = value
    msg.set_content(mail.text)
    if mail.html is not None:
        msg.add_alternative(mail.html, subtype="html")
        html_part = msg.get_payload()[1]
        for img in mail.inline:
            html_part.add_related(
                img.data,
                maintype="image",
                subtype=img.subtype,
                cid=f"<{img.cid}>",
                filename=img.filename,
                disposition="inline",
            )
    if mail.headers:
        # Long header values (List-Unsubscribe URLs) stay on one line: the
        # default 78-column fold would turn them into encoded words, which mail
        # clients do not read as URLs. RFC 5322 allows lines up to 998.
        msg.policy = msg.policy.clone(max_line_length=998)
    return msg


class MailTransport(Protocol):
    def send(self, mail: Mail) -> None: ...


class ConsoleTransport:
    def __init__(self, sender: str) -> None:
        self.sender = sender
        self._lock = threading.Lock()

    def send(self, mail: Mail) -> None:
        with self._lock:
            print(format_console(mail, self.sender), file=sys.stdout, flush=True)


def format_console(mail: Mail, sender: str) -> str:
    """Both parts as text: the plain part, then the HTML source, then a line per
    inline image (not its bytes)."""
    out = [
        "--- mail (console transport) ---",
        f"From: {sender}",
        f"To: {mail.to}",
        f"Subject: {mail.subject}",
        *(f"{name}: {value}" for name, value in mail.headers),
        "",
    ]
    if mail.html is None:
        out += [mail.text, "--- end mail ---"]
        return "\n".join(out)
    out += ["--- text/plain ---", mail.text, "--- text/html ---", mail.html]
    for img in mail.inline:
        out.append(
            f"--- inline image/{img.subtype}: cid:{img.cid} "
            f"({img.filename}, {len(img.data)} bytes) ---"
        )
    out.append("--- end mail ---")
    return "\n".join(out)


class SmtpTransport:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def send(self, mail: Mail) -> None:
        msg = build_message(mail, self.s.mail_from)
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
            if self.s.smtp_starttls:
                smtp.starttls()
            if self.s.smtp_username and self.s.smtp_password:
                smtp.login(
                    self.s.smtp_username, self.s.smtp_password.get_secret_value()
                )
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
    if settings.mail_transport == "resend":
        from blackkite.delivery.resend import ResendTransport

        return ResendTransport(settings)
    return ConsoleTransport(settings.mail_from)


_transport: MailTransport | None = None


def get_mail_transport() -> MailTransport:
    """FastAPI dependency; tests override it with a MemoryTransport."""
    global _transport
    if _transport is None:
        _transport = make_transport(get_settings())
    return _transport
