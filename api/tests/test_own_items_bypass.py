"""The caller's own private items always appear in their feed, shortlist and
calendar, hard filters included (orchestrator decision 2026-11-26); expired
ones behave like tracked items; digests and alerts still need a fit word."""

from __future__ import annotations

import pytest

from blackkite.db.models import DigestSetting
from blackkite.delivery.alerts import alert_rows
from blackkite.delivery.build import build_digest
from tests import factories as f
from tests.factories import NOW, kigali
from tests.member_helpers import *
from tests.member_helpers import fit_for, ids

FILTERS = ["stream_not_selected", "outside_rwanda", "below_min_value", "ineligible"]


def _own(db, user, title="Mine", **kw):
    kw.setdefault("deadline_at", kigali(2026, 11, 27))
    return f.opportunity(db, title, visibility="private", owner_user_id=user.id, **kw)


@pytest.mark.parametrize("reason", FILTERS)
def test_hard_filtered_own_item_stays_in_feed_shortlist_and_calendar(
    db, ana, login, reason
):
    mine = _own(db, ana)
    prof = fit_for(db, ana)
    f.score(db, ana, mine, prof, 0, fit_word=None, hard_filtered=reason)
    db.commit()
    c = login(ana.email)
    feed = {i["id"]: i for i in c.get("/api/feed").json()["items"]}
    assert str(mine.id) in feed
    assert feed[str(mine.id)]["fit"] is None
    # With the profile that filtered it, it still shows.
    assert ids(c, profile=str(prof.id)) == [str(mine.id)]
    cal = c.get("/api/calendar", params={"from": "2026-11-24", "to": "2026-11-30"})
    assert [e["id"] for d in cal.json()["days"] for e in d["entries"]] == [str(mine.id)]
    c.put(f"/api/opportunities/{mine.id}/state", json={"state": "saved"})
    assert [i["id"] for i in c.get("/api/shortlist").json()] == [str(mine.id)]


def test_hard_filtered_public_items_stay_hidden(db, ana, login):
    src = f.source(db, "Src")
    pub = f.opportunity(db, "Public", deadline_at=kigali(2026, 11, 27))
    f.link(db, pub, src)
    f.score(
        db, ana, pub, fit_for(db, ana), 0, fit_word=None, hard_filtered="outside_rwanda"
    )
    db.commit()
    assert ids(login(ana.email)) == []


def test_other_users_never_see_my_item(db, ana, ben, login):
    mine = _own(db, ana)
    f.score(
        db,
        ana,
        mine,
        fit_for(db, ana),
        0,
        fit_word=None,
        hard_filtered="outside_rwanda",
    )
    db.commit()
    assert ids(login(ben.email)) == []


def test_expired_own_item_behaves_like_a_tracked_item(db, ana, login):
    gone = _own(db, ana, "Gone", deadline_at=kigali(2026, 11, 20), status="expired")
    f.score(
        db,
        ana,
        gone,
        fit_for(db, ana),
        0,
        fit_word=None,
        hard_filtered="deadline_passed",
    )
    db.commit()
    c = login(ana.email)
    assert ids(c) == []
    assert ids(c, status="expired") == [str(gone.id)]
    cal = c.get("/api/calendar", params={"from": "2026-11-15", "to": "2026-11-30"})
    assert [e["id"] for d in cal.json()["days"] for e in d["entries"]] == [str(gone.id)]


def test_digest_and_alerts_still_need_a_fit_word(db, ana, settings):
    mine = _own(db, ana, deadline_at=kigali(2026, 11, 26))
    f.score(
        db,
        ana,
        mine,
        fit_for(db, ana),
        0,
        fit_word=None,
        hard_filtered="outside_rwanda",
    )
    setting = DigestSetting(
        user_id=ana.id, channel="email", address=ana.email, alert_min_fit="good"
    )
    db.add(setting)
    db.commit()
    built = build_digest(db, ana, settings, NOW)
    assert mine.id not in [r.opp.id for r in built.items]
    assert alert_rows(db, ana, setting, NOW) == []
