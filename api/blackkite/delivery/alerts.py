"""Urgent alerts (spec 8): an item whose best active profile's fit word is at
least the user's ``alert_min_fit`` (strong > good > possible; spec 12: the fit
word, never the numeric score), with a deadline under 5 days away, sent the day
it is found, once per item. The best profile is the one the feed shows
(member/view.py: highest-scoring non-filtered row among active profiles).
Events and investments carry no fit word (decision 24), so they never alert; an
investment of an instrument kind the user did not choose is left out in any
case (decision 54, ``build.unchosen_instrument``).

"Found" for a user is the Kigali day the item entered the catalogue or was first
scored for them (a new or edited profile can find older items). Only items found
today qualify, so an item that drifts under 5 days later is left to the digest.
A null ``alert_min_fit`` turns alerts off. The same visibility, mute, stream and state
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
    Profile,
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
    unchosen_instrument,
)
from blackkite.delivery.mail import Mail, MailTransport
from blackkite.delivery.unsubscribe import links as unsubscribe_links
from blackkite.member.view import (
    CLOSED_STATUSES,
    FIT_RANK,
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
    if setting.alert_min_fit is None:
        return []
    min_rank = FIT_RANK[setting.alert_min_fit]
    day_start = datetime.combine(kigali_today(now), time(0), KIGALI)
    # Only active profiles find items (contract section 1: the best profile is
    # chosen among active profiles; an inactive profile's rows are ignored).
    scored_today = (
        sa.select(UserOpportunityScore.opportunity_id)
        .join(
            Profile,
            sa.and_(
                Profile.id == UserOpportunityScore.profile_id,
                Profile.user_id == UserOpportunityScore.user_id,
            ),
        )
        .where(
            UserOpportunityScore.user_id == user.id,
            Profile.user_id == user.id,
            Profile.active.is_(True),
            UserOpportunityScore.created_at >= day_start,
        )
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
    unchosen = unchosen_instrument(db, user)
    rows = [
        r
        for r in rows
        if r.best is not None
        and FIT_RANK.get(r.best.fit_word or "", 0) >= min_rank
        and not unchosen(r)
    ]
    return sorted(rows, key=lambda r: (r.opp.deadline_at, r.opp.title))


FIT_PHRASES = {"strong": "a strong fit", "good": "a good or strong fit"}


def alert_view(
    rows: list[Row],
    settings: Settings,
    now: datetime,
    min_fit: str | None = None,
    *,
    unsubscribe_url: str,
) -> AlertView:
    web = settings.web_base_url.rstrip("/")
    if len(rows) == 1:
        d = rows[0].opp.deadline_at.astimezone(KIGALI).date()  # type: ignore[union-attr]
        subject = f"Closes {W.full_date(d)}: {rows[0].opp.title}"
        intro = (
            "Found today and at your alert level, so it should not wait for "
            "Monday's digest."
        )
    else:
        subject = f"{W.number_word(len(rows), True)} items close within 5 days"
        intro = (
            "Found today and at your alert level, so they should not wait for "
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
        unsubscribe_url=unsubscribe_url,
        **({"footer_line": footer_line(min_fit)} if min_fit in FIT_PHRASES else {}),
    )


def footer_line(min_fit: str) -> str:
    return (
        f"You get these alerts when an item is {FIT_PHRASES[min_fit]} for one of "
        "your profiles and closes within 5 days."
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
    if setting is None or setting.alert_min_fit is None:
        return 0
    rows = alert_rows(db, user, setting, now)
    if not rows:
        return 0
    # Before claiming anything: no alert goes out without its unsubscribe link.
    unsub = unsubscribe_links(settings, user, "alert")
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
    subject, html, text = render_alert(
        alert_view(
            rows, settings, now, setting.alert_min_fit, unsubscribe_url=unsub.page_url
        )
    )
    try:
        transport.send(
            Mail(
                to=setting.address,
                subject=subject,
                text=text,
                html=html,
                inline=(kite_image(),),
                headers=unsub.headers,
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
                DigestSetting.alert_min_fit.is_not(None),
            )
            .order_by(User.created_at)
        )
    )
