"""A personal profile's chosen instruments decide investment fit (M5 fix list 1)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa

from blackkite.db.models import Opportunity, UserOpportunityScore
from blackkite.scoring import service
from blackkite.scoring.instruments import chosen_kinds, item_kind, text_kinds
from blackkite.scoring.service import ScoringDeps
from blackkite.scoring.settings import ScoringSettings
from tests import factories as f
from tests.factories import NOW
from tests.member_helpers import *
from tests.member_helpers import ids


@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        ("treasury bonds and bills", {"treasury"}),
        ("Treasury bills", {"treasury"}),
        ("RSE shares", {"equity"}),
        ("listed equities", {"equity"}),
        ("corporate bonds", {"corporate_bond"}),
        ("real estate and land", {"real_estate"}),
        ("private deals and startups", {"private_deal"}),
        ("bonds", {"treasury", "corporate_bond"}),
        ("gold coins", set()),
        ("stock exchange listings", set()),
        ("stocks", {"equity"}),
    ],
)
def test_profile_instrument_phrases(text, kinds):
    assert text_kinds(text) == kinds


def inv(title, subtype=None, tags=(), organisation="Issuer (fictional)"):
    return Opportunity(
        id=uuid.uuid4(),
        stream="investment",
        title=title,
        subtype=subtype,
        tags=list(tags),
        organisation=organisation,
    )


@pytest.mark.parametrize(
    ("item", "kind"),
    [
        (inv("Five-year bond", subtype="treasury bond"), "treasury"),
        (inv("Bond offer", subtype="corporate bond"), "corporate_bond"),
        (inv("Offer", tags=["sector:corporate bonds"]), "corporate_bond"),
        (inv("Bond auction", organisation="National Bank of Rwanda"), "treasury"),
        (inv("Bond offer", organisation="Example Power Ltd"), "corporate_bond"),
        (inv("IPO of Example Bank on RSE"), "equity"),
        (inv("Rights issue", subtype="rights issue"), "equity"),
        (inv("Unit trust fund launch"), "fund"),
        (inv("Plots for sale in Bugesera"), "real_estate"),
        (inv("Announcement"), None),
        (
            inv(
                "Rwanda Stock Exchange listing of I&M bond",
                organisation="I&M Bank Rwanda Plc (fictional)",
            ),
            "corporate_bond",
        ),
        (
            inv(
                "Rwanda Stock Exchange listing of I&M bond",
                organisation="Rwanda Stock Exchange",
            ),
            "corporate_bond",
        ),
        (inv("Rwanda Stock Exchange listing of Example Bank shares"), "equity"),
        (inv("Rwanda Stock Exchange listing", subtype="RSE listing"), None),
        (inv("Treasury bond on the Rwanda Stock Exchange"), "treasury"),
    ],
)
def test_item_kind(item, kind):
    assert item_kind(item) == kind


def test_no_instruments_is_no_judgement():
    assert chosen_kinds({}) is None
    assert chosen_kinds({"instruments": []}) is None
    assert chosen_kinds({"instruments": ["gold coins"]}) is None


def _rows(db, user_id, profile_id):
    return {
        r.opportunity_id: r
        for r in db.scalars(
            sa.select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == user_id,
                UserOpportunityScore.profile_id == profile_id,
            )
        )
    }


def test_unchosen_instrument_ranks_below_and_is_not_under_the_profile(db, ana, login):
    """Reviewer's case: treasury and RSE chosen. The corporate bond is closer,
    on an original source, yet ranks below the treasury bond, and the feed's
    profile filter leaves it out."""
    board = f.source(db, "Board", kind="publisher")
    issuer = f.source(db, "Issuer", kind="original")
    personal = f.profile(
        db,
        ana,
        "Personal",
        type="personal",
        streams=["investment", "event"],
        instruments=["treasury bonds and bills", "RSE shares"],
    )
    treasury = f.opportunity(
        db,
        "Five-year treasury bond (fictional)",
        stream="investment",
        subtype="treasury bond",
        organisation="Example Central Bank (fictional)",
        deadline_at=NOW + timedelta(days=4),
        verification="unverified",
    )
    f.link(db, treasury, board)
    corporate = f.opportunity(
        db,
        "Corporate bond offer (fictional)",
        stream="investment",
        subtype="corporate bond",
        organisation="Example Power Company (fictional)",
        deadline_at=NOW + timedelta(days=20),
        verification="verified_original",
    )
    f.link(db, corporate, issuer, is_original=True)
    shares = f.opportunity(
        db,
        "IPO of an example bank (fictional)",
        stream="investment",
        subtype="ipo",
        deadline_at=NOW + timedelta(days=9),
        verification="unverified",
    )
    f.link(db, shares, board)
    unknown = f.opportunity(
        db,
        "Investor notice (fictional)",
        stream="investment",
        deadline_at=NOW + timedelta(days=9),
    )
    f.link(db, unknown, board)
    db.commit()

    deps = ScoringDeps(
        llm=None, embedder=None, settings=ScoringSettings(_env_file=None)
    )
    service.score_user(db, ana.id, deps=deps, now=NOW)
    db.commit()
    rows = _rows(db, ana.id, personal.id)
    assert rows[corporate.id].score < rows[treasury.id].score
    assert rows[corporate.id].score < rows[shares.id].score
    assert rows[corporate.id].score < rows[unknown.id].score
    assert rows[corporate.id].score_breakdown["fit_confidence"] == 0.1
    assert rows[treasury.id].score_breakdown["fit_confidence"] == 0.8
    assert rows[unknown.id].score_breakdown["fit_confidence"] in (0.4, 0.5)
    assert rows[corporate.id].score_reason.endswith(
        "; this profile's instruments do not include corporate bonds."
    )
    assert "do not include" not in rows[treasury.id].score_reason

    c = login(ana.email)
    under = ids(c, profile=str(personal.id), stream="investment")
    assert str(corporate.id) not in under
    assert {str(treasury.id), str(shares.id), str(unknown.id)} <= set(under)
    # Without the profile filter the item is still in the feed (not filtered).
    assert str(corporate.id) in ids(c, stream="investment")
