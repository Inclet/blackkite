"""Pending backfills (spec 5: a new user or an edited profile triggers a backfill
of match and score). Requests are recorded here, in the HTTP request; the worker
runs them on a later tick (worker/backfills.py), never the request itself, so a
burst of edits costs one backfill and no request waits on the model (cost guard).

What asks for a backfill (member/profiles.py):

* a new active profile;
* a change to its type or data (streams included) while active;
* activation, always (decision 36): items may have arrived while the profile
  was off and the worker skips inactive profiles; judgement reuse keeps the
  catch-up cheap;
* a mute or unmute: every active profile of that user (``muted_source_only``).

A rename or a deactivation asks for nothing. Each request stamps
``backfill_requested_at``; the worker runs a profile once the newest stamp is at
least ``BACKFILL_DEBOUNCE`` old, so a run of quick edits costs one backfill.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import OpportunitySource, Profile, UserOpportunityScore

BACKFILL_DEBOUNCE = timedelta(seconds=60)


def request_backfill(profile: Profile, now: datetime) -> None:
    """Mark one profile (ORM object, saved by the caller's commit)."""
    profile.backfill_requested_at = now
    profile.backfill_attempts = 0


def request_user_rescore(db: Session, user_id: uuid.UUID, now: datetime) -> int:
    """Mark every active profile of one user. Not an edit: ``updated_at`` stays.
    Returns how many were marked; the caller commits."""
    return db.execute(
        sa.update(Profile)
        .where(Profile.user_id == user_id, Profile.active.is_(True))
        .values(
            backfill_requested_at=now,
            backfill_attempts=0,
            updated_at=Profile.updated_at,
        )
        .execution_options(synchronize_session=False)
    ).rowcount


def clear_muted_rows(db: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> int:
    """After an unmute: drop this user's ``muted_source_only`` rows for items the
    source carries, so they show again at once (unscored) instead of staying
    hidden until the worker re-scores them. Those rows hold no model judgement.
    Items still carried only by muted sources stay hidden (the feed applies
    mutes at query time). The caller commits."""
    return db.execute(
        sa.delete(UserOpportunityScore)
        .where(
            UserOpportunityScore.user_id == user_id,
            UserOpportunityScore.score_breakdown["hard_filtered"].astext
            == "muted_source_only",
            UserOpportunityScore.opportunity_id.in_(
                sa.select(OpportunitySource.opportunity_id).where(
                    OpportunitySource.source_id == source_id
                )
            ),
        )
        .execution_options(synchronize_session=False)
    ).rowcount
