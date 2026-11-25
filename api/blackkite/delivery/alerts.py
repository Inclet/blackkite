"""Urgent alerts (spec 8): an item whose best score is above the user's
``alert_threshold``, with a deadline under 5 days away, sent the day it is found,
once per item.

"Found" for a user is the Kigali day the item entered the catalogue or was first
scored for them (a new or edited profile can find older items). Only items found
today qualify, so an item that drifts under 5 days later is left to the digest.
A null threshold turns alerts off. The same visibility, mute, stream and state
rules as the digest apply.

One email per user per run lists every new qualifying item. ``alert_log``
(unique per user and item) is written before the mail goes and rolled back if it
fails, so an item is alerted at most once even with two workers.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from blackkite.config import Settings
from blackkite.db.models import (
    AlertLog,
    DigestSetting,
    Opportunity,
    User,
    UserOpportunity,
    UserOpportunityScore,
)
from blackkite.delivery import wording as W
from blackkite.delivery.alert import AlertView, render_alert
from blackkite.delivery.build import (
    EXCLUDED_STATES,
    SETTINGS_PATH,
    digest_item,
    email_setting,
    kite_image,
)
from blackkite.delivery.mail import Mail, MailTransport
from blackkite.member.view import (
    CLOSED_STATUSES,
    Row,
    kigali_today,
    load_rows,
    member_visible,
    not_only_muted,
)
from blackkite.pipeline.dates import KIGALI

log = logging.getLogger("blackkite.delivery")

ALERT_WINDOW = timedelta(days=5)
HEADING = "Closing within 5 days"


def alert_rows(
    db: Session, user: User, setting: DigestSetting, now: datetime
) -> list[Row]:
    threshold = setting.alert_threshold
    if threshold is None:
        return []
    day_start = datetime.combine(kigali_today(now), time(0), KIGALI)
    scored_today = sa.select(UserOpportunityScore.opportunity_id).where(
        UserOpportunityScore.user_id == user.id,
        UserOpportunityScore.created_at >= day_start,
    )
    q = sa.select(Opportunity).where(
        member_visible(user.id),
        not_only_muted(user.id),
        Opportunity.status.not_in(CLOSED_STATUSES),
        Opportunity.deadline_at > now,
        Opportunity.deadline_at < now + ALERT_WINDOW,
        sa.or_(Opportunity.created_at >= day_start, Opportunity.id.in_(scored_today)),
        Opportunity.id.not_in(
            sa.select(AlertLog.opportunity_id).where(AlertLog.user_id == user.id)
        ),
        Opportunity.id.not_in(
            sa.select(UserOpportunity.opportunity_id).where(
                UserOpportunity.user_id == user.id,
                UserOpportunity.state.in_(EXCLUDED_STATES),
            )
        ),
    )
    if setting.streams:
        q = q.where(Opportunity.stream.in_(setting.streams))
    rows = load_rows(db, user, db.scalars(q).all())
    rows = [
        r
        for r in rows
        if r.best is not None and r.best.score is not None and r.best.score > threshold
    ]
    return sorted(rows, key=lambda r: (r.opp.deadline_at, r.opp.title))


def alert_view(rows: list[Row], settings: Settings, now: datetime) -> AlertView:
    web = settings.web_base_url.rstrip("/")
    if len(rows) == 1:
        d = rows[0].opp.deadline_at.astimezone(KIGALI).date()  # type: ignore[union-attr]
        subject = f"Closes {W.full_date(d)}: {rows[0].opp.title}"
        intro = (
            "Found today and above your alert level, so it should not wait for "
            "Monday's digest."
        )
    else:
        subject = f"{W.number_word(len(rows), True)} items close within 5 days"
        intro = (
            "Found today and above your alert level, so they should not wait for "
            "Monday's digest."
        )
    return AlertView(
        subject=subject,
        issue_date=kigali_today(now),
        heading=HEADING,
        intro=intro,
        items=[digest_item(r, web) for r in rows],
        cta_url=f"{web}/",
        settings_url=f"{web}{SETTINGS_PATH}",
    )


def send_alerts(
    db: Session,
    user: User,
    settings: Settings,
    transport: MailTransport,
    now: datetime,
) -> int:
    """Send today's new urgent alerts for one user; returns how many items went
    out. Commits."""
    if user.status != "active":
        return 0
    setting = email_setting(db, user)
    if setting is None or setting.alert_threshold is None:
        return 0
    rows = alert_rows(db, user, setting, now)
    if not rows:
        return 0
    claimed = set(
        db.scalars(
            insert(AlertLog)
            .values(
                [
                    {
                        "user_id": user.id,
                        "opportunity_id": r.opp.id,
                        "profile_id": r.best.profile_id if r.best else None,
                        "sent_at": now,
                    }
                    for r in rows
                ]
            )
            .on_conflict_do_nothing(index_elements=["user_id", "opportunity_id"])
            .returning(AlertLog.opportunity_id)
        )
    )
    rows = [r for r in rows if r.opp.id in claimed]
    if not rows:
        db.rollback()
        return 0
    subject, html, text = render_alert(alert_view(rows, settings, now))
    try:
        transport.send(
            Mail(
                to=setting.address,
                subject=subject,
                text=text,
                html=html,
                inline=(kite_image(),),
            )
        )
    except Exception:
        db.rollback()
        raise
    db.commit()
    return len(rows)


def users_with_alerts(db: Session) -> list[User]:
    return list(
        db.scalars(
            sa.select(User)
            .join(DigestSetting, DigestSetting.user_id == User.id)
            .where(
                User.status == "active",
                DigestSetting.channel == "email",
                DigestSetting.alert_threshold.is_not(None),
            )
            .order_by(User.created_at)
        )
    )
