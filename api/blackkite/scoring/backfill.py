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
  An unmute is due at the next tick, without the debounce. Until then the feed
  treats the user's ``muted_source_only`` rows on items no longer carried only by
  muted sources as unscored (member/view.py), so they show again at once. The
  rows are rescored in place, never deleted, so ``created_at`` (the alerts'
  "found today") stays and an old item cannot alert because of an unmute.

A rename or a deactivation asks for nothing. Each request stamps
``backfill_requested_at``; the worker runs a profile once the newest stamp is at
least ``BACKFILL_DEBOUNCE`` old, so a run of quick edits costs one backfill.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import Profile

BACKFILL_DEBOUNCE = timedelta(seconds=60)


def request_backfill(profile: Profile, now: datetime) -> None:
    """Mark one profile (ORM object, saved by the caller's commit)."""
    profile.backfill_requested_at = now
    profile.backfill_attempts = 0


def request_user_rescore(
    db: Session, user_id: uuid.UUID, now: datetime, *, immediate: bool = False
) -> int:
    """Mark every active profile of one user. Not an edit: ``updated_at`` stays.
    With ``immediate`` the request skips the debounce and is due on the next
    worker tick (an unmute). Returns how many were marked; the caller commits."""
    if immediate:
        now = now - BACKFILL_DEBOUNCE
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
