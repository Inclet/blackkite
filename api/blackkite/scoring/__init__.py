"""STUB. Placeholder for the scoring track's package, replaced at merge.

The member API calls ``backfill_profile`` after a profile is created or edited
(spec 5: an edited profile triggers a backfill of match and score). This stub does
nothing; the scoring track owns the real implementation.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session


def backfill_profile(session: Session, profile_id: uuid.UUID) -> None:  # STUB
    """STUB: does nothing until the scoring track's version is merged."""
