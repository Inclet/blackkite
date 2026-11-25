"""Worker jobs for delivery: the weekly digest (Monday, Africa/Kigali, at
``BK_DIGEST_HOUR``, default 07:00) and urgent alerts (after each ingest and score
cycle). Each runs under its own Postgres advisory lock, so two workers never send
at once, and each is idempotent per user per day (digest_log unique per Kigali day;
alert_log unique per item). One user's failure never stops the others.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from blackkite.config import Settings
from blackkite.db.models import User
from blackkite.delivery.alerts import send_alerts, users_with_alerts
from blackkite.delivery.build import send_digest
from blackkite.delivery.mail import MailTransport
from blackkite.pipeline.dates import KIGALI
from blackkite.worker.runner import JOB_LOCK_NAMESPACE, advisory_lock

log = logging.getLogger("blackkite.delivery")

DIGEST_LOCK_KEY = 2
ALERTS_LOCK_KEY = 3
MONDAY = 0


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
            except Exception:
                s.rollback()
                log.exception("alerts for user %s failed", user.id)
    return sent
