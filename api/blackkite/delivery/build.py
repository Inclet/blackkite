"""Weekly digest from the user's scores (spec 8; docs/api-contract.md section 3).

What goes in:

* **Top items** across the user's active profiles: visible to them (member rule,
  pipeline/visibility.py), not carried only by sources they muted, still open,
  not dismissed or done, in the streams of their digest setting (all streams when
  unset), with at least one non-filtered score row. Tenders and funding also need
  a fit word (contract section 1: below "possible" is not shown). Ranked by the
  best profile's score, then closing soonest. At most 12, and at most 3
  investments and 3 events (spec 7.1).
* **Instruments** (decision 54): an investment item whose instrument kind none of
  the user's active profiles that follow investments chose is left out
  (``unchosen_instrument``). Items of an unrecognised kind, profiles with no
  instruments listed, and the user's own items stay. The feed still lists them,
  ranked lower.
* An item that went out in the **previous** digest is left out unless its
  deadline or value changed since.
* **Closing in 7 days**: the user's saved and acting items whose deadline (events:
  first day) falls in the next 7 days, soonest first. They are not repeated in
  the top items.
* ``more_count``: eligible items not shown ("N more are waiting there").

Nothing is sent when there is nothing to show. Every send stores a digest_log row
for (user, Kigali day); a second run that day sends nothing (the unique key).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from blackkite.config import Settings
from blackkite.db.models import (
    DigestLog,
    DigestSetting,
    Opportunity,
    Profile,
    Source,
    SourceRun,
    User,
    UserOpportunity,
)
from blackkite.delivery import wording as W
from blackkite.delivery.digest import (
    DigestFooter,
    DigestItem,
    DigestView,
    render_digest,
)
from blackkite.delivery.logo import kite_png
from blackkite.delivery.mail import InlineImage, Mail, MailTransport
from blackkite.delivery.unsubscribe import links as unsubscribe_links
from blackkite.member.view import (
    CLOSED_STATUSES,
    SCORED_STREAMS,
    SHORTLIST_STATES,
    Row,
    first_name,
    is_closed,
    kigali_today,
    load_rows,
    member_visible,
    not_only_muted,
    sort_date,
    trust_for,
)
from blackkite.scoring import instruments

log = logging.getLogger("blackkite.delivery")

DIGEST_CAP = 12
STREAM_CAPS = {"investment": 3, "event": 3}
CLOSING_DAYS = 7
FREQUENCY_PHRASE = "every Monday"
# The web's digest settings screen: "Change how often" and the alert email's
# settings link go there. "Stop these emails" is a signed one-click link
# (decision 43, delivery/unsubscribe.py).
SETTINGS_PATH = "/settings/digest"
EXCLUDED_STATES = ("dismissed", "done")


def kite_image() -> InlineImage:
    return InlineImage(cid="kite-logo", data=kite_png(), filename="kite.png")


def email_setting(db: Session, user: User) -> DigestSetting | None:
    return db.scalar(
        sa.select(DigestSetting).where(
            DigestSetting.user_id == user.id, DigestSetting.channel == "email"
        )
    )


def _is_http(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https")
        and bool(parts.hostname)
        and url == url.strip()
        and not any(ord(c) < 0x21 or ord(c) == 0x7F for c in url)
    )


def item_url(row: Row, web_base_url: str) -> str:
    """The original notice (else the first visible source); the item's page in
    the app for items with no source link (private manual items)."""
    links = row.links
    original = next((ln for ln in links if ln.is_original), None)
    for ln in ([original] if original else []) + links:
        if _is_http(ln.url):
            return ln.url
    return f"{web_base_url.rstrip('/')}/o/{row.opp.id}"


def date_line(opp: Opportunity) -> str:
    if opp.stream == "event" and opp.event_start is not None:
        return W.event_line(opp.event_start, opp.event_end)
    if opp.deadline_at is not None:
        return W.deadline_line(opp.deadline_at)
    return "No deadline" if opp.stream == "investment" else "No deadline stated"


def summary(row: Row) -> str:
    """Organisation (events: venue) and the one-line reason it matched."""
    o = row.opp
    lead = (o.location or o.organisation) if o.stream == "event" else o.organisation
    parts = [W.sentence(lead)] if lead else []
    reason = row.best.one_line_reason if row.best else None
    if reason:
        parts.append(W.sentence(reason))
    return " ".join(parts) or W.sentence(o.title)


def digest_item(row: Row, web_base_url: str) -> DigestItem:
    o = row.opp
    trust = trust_for(row).state
    return DigestItem(
        stream=o.stream,
        profile_label=row.best.profile_name if row.best else None,
        provisional=bool(row.best and row.best.provisional),
        title=o.title,
        url=item_url(row, web_base_url),
        summary=summary(row),
        date_line=date_line(o),
        trust_note=W.TRUST_NOTES.get(trust),
        value_line=W.value_line(o.value_amount, o.value_currency, o.value_note),
    )


def snapshot(o: Opportunity) -> dict[str, Any]:
    return {
        "deadline_at": o.deadline_at.isoformat() if o.deadline_at else None,
        "value_amount": str(o.value_amount) if o.value_amount is not None else None,
        "value_currency": o.value_currency,
    }


def _changed_since(o: Opportunity, sent: dict[str, Any]) -> bool:
    """Deadline or value differ from what went out."""
    now = snapshot(o)
    if (now["deadline_at"] is None) != (sent.get("deadline_at") is None):
        return True
    if now["deadline_at"] and datetime.fromisoformat(now["deadline_at"]) != (
        datetime.fromisoformat(sent["deadline_at"])
    ):
        return True
    return (now["value_amount"], now["value_currency"]) != (
        sent.get("value_amount"),
        sent.get("value_currency"),
    )


def previous_items(db: Session, user: User, today) -> dict[str, dict[str, Any]]:
    """Items of the user's last digest before today, by id."""
    last = db.scalar(
        sa.select(DigestLog)
        .where(DigestLog.user_id == user.id, DigestLog.digest_date < today)
        .order_by(DigestLog.digest_date.desc())
        .limit(1)
    )
    if last is None:
        return {}
    return {i["id"]: i for i in (last.details or {}).get("items", []) if "id" in i}


def _open_rows(
    db: Session,
    user: User,
    now: datetime,
    *,
    states: tuple[str, ...] | None,
    streams: list[str] | None,
    keep_filtered: bool,
) -> list[Row]:
    mine = sa.select(UserOpportunity.opportunity_id).where(
        UserOpportunity.user_id == user.id
    )
    q = sa.select(Opportunity).where(
        member_visible(user.id),
        not_only_muted(user.id),
        Opportunity.status.not_in(CLOSED_STATUSES),
    )
    if states is None:
        q = q.where(
            Opportunity.id.not_in(
                mine.where(UserOpportunity.state.in_(EXCLUDED_STATES))
            )
        )
    else:
        q = q.where(Opportunity.id.in_(mine.where(UserOpportunity.state.in_(states))))
    if streams:
        q = q.where(Opportunity.stream.in_(streams))
    opps = [o for o in db.scalars(q).all() if not is_closed(o, now)]
    return load_rows(db, user, opps, keep_filtered=keep_filtered)


def unchosen_instrument(db: Session, user: User):
    """A predicate on rows: True for an investment item of a kind the user did
    not choose (decision 54), judged on the user's active profiles that follow
    investments (or list no streams). It is unchosen only when every one of them
    lists instruments and none names the item's kind; an unrecognised kind or
    the user's own item is never unchosen."""
    datas = [
        d or {}
        for d in db.scalars(
            sa.select(Profile.data).where(
                Profile.user_id == user.id, Profile.active.is_(True)
            )
        )
    ]
    following = []
    for d in datas:
        streams = d.get("streams")
        if not (isinstance(streams, list) and streams) or "investment" in streams:
            following.append(d)

    def unchosen(row: Row) -> bool:
        if row.opp.stream != "investment" or row.own or not following:
            return False
        return all(
            instruments.instrument_chosen(row.opp, d) is False for d in following
        )

    return unchosen


def eligible(row: Row) -> bool:
    if row.best is None:
        return False
    return row.opp.stream not in SCORED_STREAMS or row.best.fit_word is not None


def rank_key(row: Row, now: datetime) -> tuple[Any, ...]:
    d = sort_date(row.opp)
    return (
        -(row.best.rank if row.best else -1),
        d is None,
        d or now.date(),
        row.opp.title,
    )


def active_sources_checked(db: Session, now: datetime) -> int:
    """Active sources with a successful run in the past 7 days."""
    return (
        db.scalar(
            sa.select(sa.func.count(sa.distinct(SourceRun.source_id)))
            .join(Source, Source.id == SourceRun.source_id)
            .where(
                Source.status == "active",
                SourceRun.status == "succeeded",
                SourceRun.finished_at >= now - timedelta(days=7),
            )
        )
        or 0
    )


@dataclass
class BuiltDigest:
    view: DigestView | None
    items: list[Row] = field(default_factory=list)
    closing: list[Row] = field(default_factory=list)
    more_count: int = 0
    # List-Unsubscribe headers for the mail (decision 43).
    headers: tuple[tuple[str, str], ...] = ()

    @property
    def opportunity_ids(self) -> list[uuid.UUID]:
        return [r.opp.id for r in self.items + self.closing]

    def details(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": str(r.opp.id),
                    "profile_id": str(r.best.profile_id) if r.best else None,
                    **snapshot(r.opp),
                }
                for r in self.items
            ],
            "closing": [str(r.opp.id) for r in self.closing],
            "more_count": self.more_count,
        }


def _subject(items: list[Row], closing: list[Row], total: int, now: datetime) -> str:
    today = kigali_today(now)
    if total == 0:
        n = len(closing)
        return f"{W.number_word(n, True)} saved {W.plural(n, 'item closes', 'items close')} within 7 days"
    text = (
        f"{W.number_word(total, True)} {W.plural(total, 'thing', 'things')} this week"
    )
    soon = [
        r
        for r in items
        if r.opp.deadline_at is not None
        and today
        <= r.opp.deadline_at.astimezone(W.KIGALI).date()
        <= today + timedelta(days=CLOSING_DAYS)
    ]
    if len(soon) == 1:
        text += f", one closing {soon[0].opp.deadline_at.astimezone(W.KIGALI):%A}"
    elif soon:
        text += f", {W.number_word(len(soon))} closing within a week"
    return text


def _intro(shown: int, total: int) -> str:
    if total == 0:
        return "Nothing new made your list this week. These saved items close soon."
    first = f"{W.number_word(total, True)} {W.plural(total, 'thing', 'things')} made your list this week."
    if shown == total:
        return first
    if shown == 1:
        return f"{first} Here is the one to look at first."
    return f"{first} Here are the {W.number_word(shown)} to look at first."


def build_digest(
    db: Session, user: User, settings: Settings, now: datetime
) -> BuiltDigest:
    today = kigali_today(now)
    setting = email_setting(db, user)
    streams = setting.streams if setting else None
    web = settings.web_base_url.rstrip("/")

    closing_rows = _open_rows(
        db, user, now, states=SHORTLIST_STATES, streams=None, keep_filtered=True
    )
    last_day = today + timedelta(days=CLOSING_DAYS)
    closing = sorted(
        [
            r
            for r in closing_rows
            if (d := sort_date(r.opp)) is not None and today <= d <= last_day
        ],
        key=lambda r: (sort_date(r.opp), r.opp.title),
    )
    closing_ids = {r.opp.id for r in closing}

    previous = previous_items(db, user, today)
    unchosen = unchosen_instrument(db, user)
    candidates = [
        r
        for r in _open_rows(
            db, user, now, states=None, streams=streams, keep_filtered=False
        )
        if eligible(r) and r.opp.id not in closing_ids and not unchosen(r)
    ]
    candidates.sort(key=lambda r: rank_key(r, now))
    shown: list[Row] = []
    per_stream: dict[str, int] = {}
    for r in candidates:
        sent = previous.get(str(r.opp.id))
        if sent is not None and not _changed_since(r.opp, sent):
            continue
        cap = STREAM_CAPS.get(r.opp.stream)
        if cap is not None and per_stream.get(r.opp.stream, 0) >= cap:
            continue
        if len(shown) >= DIGEST_CAP:
            break
        shown.append(r)
        per_stream[r.opp.stream] = per_stream.get(r.opp.stream, 0) + 1
    more = len(candidates) - len(shown)

    built = BuiltDigest(view=None, items=shown, closing=closing, more_count=more)
    if not shown and not closing:
        return built
    total = len(shown) + more
    unsub = unsubscribe_links(settings, user, "digest")
    built.headers = unsub.headers
    built.view = DigestView(
        subject=_subject(shown, closing, total, now),
        first_name=first_name(user),
        issue_date=today,
        greeting=W.greeting(now),
        intro=_intro(len(shown), total),
        items=[digest_item(r, web) for r in shown],
        closing_soon=[digest_item(r, web) for r in closing],
        cta_url=f"{web}/",
        more_count=more,
        footer=DigestFooter(
            source_count=active_sources_checked(db, now),
            frequency=FREQUENCY_PHRASE,
            change_frequency_url=f"{web}{SETTINGS_PATH}",
            unsubscribe_url=unsub.page_url,
        ),
    )
    return built


def digest_mail(
    view: DigestView, to: str, headers: tuple[tuple[str, str], ...] = ()
) -> Mail:
    subject, html, text = render_digest(view)
    return Mail(
        to=to,
        subject=subject,
        text=text,
        html=html,
        inline=(kite_image(),),
        headers=headers,
    )


@dataclass(frozen=True)
class SendOutcome:
    status: str  # sent | empty | off | already_sent | inactive
    log_id: uuid.UUID | None = None


def send_digest(
    db: Session,
    user: User,
    settings: Settings,
    transport: MailTransport,
    now: datetime,
    *,
    respect_frequency: bool = True,
) -> SendOutcome:
    """Build, log and send one user's digest for today (Kigali). Idempotent per
    user per day: the digest_log row is written (unique per day) before the mail
    goes, and rolled back if sending fails. Commits."""
    if user.status != "active":
        return SendOutcome("inactive")
    setting = email_setting(db, user)
    if respect_frequency and setting is not None and setting.frequency == "off":
        return SendOutcome("off")
    today = kigali_today(now)
    already = db.scalar(
        sa.select(DigestLog.id).where(
            DigestLog.user_id == user.id, DigestLog.digest_date == today
        )
    )
    if already is not None:
        return SendOutcome("already_sent", already)
    built = build_digest(db, user, settings, now)
    if built.view is None:
        return SendOutcome("empty")
    entry = DigestLog(
        user_id=user.id,
        sent_at=now,
        digest_date=today,
        opportunity_ids=built.opportunity_ids,
        details=built.details(),
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return SendOutcome("already_sent")
    address = setting.address if setting is not None else user.email
    try:
        transport.send(digest_mail(built.view, address, built.headers))
    except Exception:
        db.rollback()
        raise
    db.commit()
    return SendOutcome("sent", entry.id)
