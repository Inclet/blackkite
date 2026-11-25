"""Worker jobs for delivery: the weekly digest (Monday, Africa/Kigali, at
``BK_DIGEST_HOUR``, default 07:00) and urgent alerts (after each ingest and score
cycle). Each runs under its own Postgres advisory lock, so two workers never send
at once, and each is idempotent per user per day (digest_log unique per Kigali day;
alert_log unique per item). One user's failure never stops the others.

A send the configuration refuses (real sending switched off, Resend or the
unsubscribe secret not configured) is not an error to repeat: the job retries
it on later ticks, but logs the refusal once per user per kind per Kigali day
(``RefusalLog``, per worker process).
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from blackkite.config import Settings
from blackkite.db.models import User
from blackkite.delivery.alerts import send_alerts, users_with_alerts
from blackkite.delivery.build import send_digest
from blackkite.delivery.mail import MailTransport
from blackkite.delivery.resend import RealSendDisabled, ResendNotConfigured
from blackkite.delivery.unsubscribe import UnsubscribeNotConfigured
from blackkite.pipeline.dates import KIGALI
from blackkite.worker.runner import JOB_LOCK_NAMESPACE, advisory_lock

log = logging.getLogger("blackkite.delivery")

DIGEST_LOCK_KEY = 2
ALERTS_LOCK_KEY = 3
MONDAY = 0


# Exceptions that mean "the configuration does not allow sending", not a failure.
REFUSALS = (RealSendDisabled, ResendNotConfigured, UnsubscribeNotConfigured)


class RefusalLog:
    """Logs a refused send once per (user, kind) per Kigali day."""

    def __init__(self) -> None:
        self._seen: set[tuple[uuid.UUID, str, date]] = set()
        self._lock = threading.Lock()

    def note(self, user_id: uuid.UUID, kind: str, at: datetime, exc: Exception) -> bool:
        """Log the refusal unless already logged today; True if it was logged."""
        day = at.astimezone(KIGALI).date()
        key = (user_id, kind, day)
        with self._lock:
            if key in self._seen:
                return False
            self._seen = {k for k in self._seen if k[2] >= day}
            self._seen.add(key)
        log.warning(
            "%s for user %s not sent: %s (%s); logged once today",
            kind,
            user_id,
            exc,
            type(exc).__name__,
        )
        return True


refusals = RefusalLog()


def _now() -> datetime:
    return datetime.now(UTC)


def digest_due(now: datetime, hour: int) -> bool:
    local = now.astimezone(KIGALI)
    return local.weekday() == MONDAY and local.hour >= hour


def weekly_digest_job(
    sessions: sessionmaker[Session],
    settings: Settings,
    transport: MailTransport,
    now: Callable[[], datetime] = _now,
) -> Counter[str] | None:
    """Send every active user's digest if it is Monday (Kigali) at or after the
    digest hour. Safe to run at any time and repeatedly (start-up catch-up).
    Returns outcome counts, or None if another worker holds the lock."""
    at = now()
    counts: Counter[str] = Counter()
    if not digest_due(at, settings.digest_hour):
        return counts
    with (
        sessions() as s,
        advisory_lock(s.get_bind(), JOB_LOCK_NAMESPACE, DIGEST_LOCK_KEY) as got,
    ):
        if not got:
            return None
        users = s.scalars(
            sa.select(User).where(User.status == "active").order_by(User.created_at)
        ).all()
        for user in users:
            try:
                counts[send_digest(s, user, settings, transport, at).status] += 1
            except REFUSALS as exc:
                s.rollback()
                counts["refused"] += 1
                refusals.note(user.id, "digest", at, exc)
            except Exception:
                s.rollback()
                counts["failed"] += 1
                log.exception("digest for user %s failed", user.id)
    return counts


def alerts_job(
    sessions: sessionmaker[Session],
    settings: Settings,
    transport: MailTransport,
    now: Callable[[], datetime] = _now,
) -> int | None:
    """Send today's new urgent alerts to every user who has them on. Returns how
    many items went out, or None if another worker holds the lock."""
    at = now()
    sent = 0
    with (
        sessions() as s,
        advisory_lock(s.get_bind(), JOB_LOCK_NAMESPACE, ALERTS_LOCK_KEY) as got,
    ):
        if not got:
            return None
        for user in users_with_alerts(s):
            try:
                sent += send_alerts(s, user, settings, transport, at)
            except REFUSALS as exc:
                s.rollback()
                refusals.note(user.id, "alert", at, exc)
            except Exception:
                s.rollback()
                log.exception("alerts for user %s failed", user.id)
    return sent
