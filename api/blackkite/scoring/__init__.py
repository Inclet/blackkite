"""Per-user stages 7 and 8 (CLAUDE.md sections 5 and 7): match and score.

``blackkite.scoring.service`` is the entry point: ``score_new_opportunities`` (the
worker, after ingest), ``backfill_profile`` (a new or edited profile) and
``score_user`` (``bk score``). Rows go to ``user_opportunity_score`` in the shape
fixed by docs/api-contract.md section 1; ``user_opportunity`` is never touched.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session


def backfill_profile(session: Session, profile_id: uuid.UUID, **kwargs: Any) -> Any:
    """Re-score a new or edited profile against open items (spec 5). See service.backfill_profile."""
    from blackkite.scoring import service

    return service.backfill_profile(session, profile_id, **kwargs)


def score_user(session: Session, user_id: uuid.UUID, **kwargs: Any) -> Any:
    """Re-score every active profile of one user. See service.score_user."""
    from blackkite.scoring import service

    return service.score_user(session, user_id, **kwargs)


def score_new_opportunities(session: Session, since: datetime, **kwargs: Any) -> Any:
    """Score items created or updated since ``since`` for every user. See the service."""
    from blackkite.scoring import service

    return service.score_new_opportunities(session, since, **kwargs)


__all__ = ["backfill_profile", "score_new_opportunities", "score_user"]
