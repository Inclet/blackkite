"""Account export and deletion (spec 10: "allow account export and deletion").

Export: everything stored about the caller, as JSON: account, profiles, digest
settings, item states and notes, private items, digest and alert logs, source
suggestions and mutes. Numeric scores are internal (spec 12) and left out.

Deletion: the user row and, through ON DELETE CASCADE, every per-user row
(sessions, login tokens, profiles and their scores, digest settings, states and
notes, digest and alert logs, suggestions, mutes) and the private items they own.
Shared catalogue rows stay; references to the user from shared rows (who added a
source, who invited whom, who reviewed a suggestion) become NULL. Invites sent to
the user's address are deleted too, since they hold the address. The last active
admin cannot delete their account (nobody could manage the platform after).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import (
    AlertLog,
    DigestLog,
    DigestSetting,
    Invite,
    Opportunity,
    Profile,
    Source,
    SourceSuggestion,
    User,
    UserOpportunity,
    UserSourceMute,
)
from blackkite.member.profiles import data_out

# Opportunity columns in the export of the caller's private items.
PRIVATE_ITEM_FIELDS = (
    "id",
    "stream",
    "subtype",
    "title",
    "organisation",
    "summary",
    "published_at",
    "deadline_at",
    "event_start",
    "event_end",
    "value_amount",
    "value_currency",
    "value_note",
    "location",
    "eligibility",
    "requirements",
    "submission_method",
    "fees",
    "tags",
    "status",
    "created_at",
    "updated_at",
)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)


def _json(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    return str(v)


def export(db: Session, user: User) -> dict[str, Any]:
    uid = user.id
    profiles = db.scalars(
        sa.select(Profile).where(Profile.user_id == uid).order_by(Profile.created_at)
    )
    settings = db.scalars(sa.select(DigestSetting).where(DigestSetting.user_id == uid))
    states = db.execute(
        sa.select(UserOpportunity, Opportunity.title)
        .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
        .where(UserOpportunity.user_id == uid)
        .order_by(UserOpportunity.created_at)
    ).all()
    private = db.scalars(
        sa.select(Opportunity)
        .where(Opportunity.visibility == "private", Opportunity.owner_user_id == uid)
        .order_by(Opportunity.created_at)
    )
    digests = db.scalars(
        sa.select(DigestLog).where(DigestLog.user_id == uid).order_by(DigestLog.sent_at)
    )
    alerts = db.scalars(
        sa.select(AlertLog).where(AlertLog.user_id == uid).order_by(AlertLog.sent_at)
    )
    suggestions = db.scalars(
        sa.select(SourceSuggestion)
        .where(SourceSuggestion.user_id == uid)
        .order_by(SourceSuggestion.created_at)
    )
    mutes = db.execute(
        sa.select(UserSourceMute.source_id, Source.name)
        .join(Source, Source.id == UserSourceMute.source_id)
        .where(UserSourceMute.user_id == uid)
    ).all()
    return _json(
        {
            "exportedAt": datetime.now(UTC),
            "account": {
                "id": str(uid),
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "status": user.status,
                "createdAt": user.created_at,
                "lastSignInAt": user.last_sign_in_at,
            },
            "profiles": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "type": p.type,
                    "data": data_out(p.type, p.data or {}),
                    "version": p.version,
                    "active": p.active,
                    "createdAt": p.created_at,
                    "updatedAt": p.updated_at,
                }
                for p in profiles
            ],
            "digestSettings": [
                {
                    "channel": s.channel,
                    "address": s.address,
                    "frequency": s.frequency,
                    "day": s.day,
                    "alertMinFit": s.alert_min_fit,
                    "streams": s.streams,
                }
                for s in settings
            ],
            "states": [
                {
                    "opportunityId": str(uo.opportunity_id),
                    "title": title,
                    "state": uo.state,
                    "dismissReason": uo.dismiss_reason,
                    "note": uo.note,
                    "updatedAt": uo.updated_at,
                }
                for uo, title in states
            ],
            "privateItems": [
                {_camel(k): getattr(o, k) for k in PRIVATE_ITEM_FIELDS} for o in private
            ],
            "digestLog": [
                {
                    "digestDate": d.digest_date.isoformat(),
                    "sentAt": d.sent_at,
                    "opportunityIds": [str(i) for i in d.opportunity_ids],
                }
                for d in digests
            ],
            "alertLog": [
                {"opportunityId": str(a.opportunity_id), "sentAt": a.sent_at}
                for a in alerts
            ],
            "sourceSuggestions": [
                {
                    "url": s.url,
                    "note": s.note,
                    "status": s.status,
                    "createdAt": s.created_at,
                }
                for s in suggestions
            ],
            "mutedSources": [{"sourceId": str(sid), "name": n} for sid, n in mutes],
        }
    )


class LastAdmin(Exception):
    pass


def delete_account(db: Session, user: User) -> None:
    """Delete the caller and all their per-user rows. Commits."""
    if user.role == "admin":
        others = db.scalar(
            sa.select(sa.func.count())
            .select_from(User)
            .where(User.role == "admin", User.status == "active", User.id != user.id)
        )
        if not others:
            raise LastAdmin
    db.execute(
        sa.delete(Invite).where(sa.func.lower(Invite.email) == user.email.lower())
    )
    db.execute(sa.delete(User).where(User.id == user.id))
    db.commit()
