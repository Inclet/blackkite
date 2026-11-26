"""Feed filters per spec 8 (docs/api-contract.md section 5): stream, profile,
status, deadline window, fit (at least), source, verification, together."""

from __future__ import annotations

from tests import factories as f
from tests.factories import kigali
from tests.member_helpers import *
from tests.member_helpers import fit_for, ids


def _catalogue(db, ana):
    one = f.source(db, "One", kind="original")
    two = f.source(db, "Two")
    strong = f.opportunity(
        db,
        "Strong tender",
        deadline_at=kigali(2026, 11, 28),
        verification="verified_original",
    )
    f.link(db, strong, one, is_original=True)
    good = f.opportunity(db, "Good tender", deadline_at=kigali(2026, 12, 20))
    f.link(db, good, two)
    possible = f.opportunity(
        db, "Possible funding", stream="funding", deadline_at=kigali(2026, 11, 27)
    )
    f.link(db, possible, two)
    event = f.opportunity(
        db, "Event", stream="event", event_start=kigali(2026, 11, 29, 9)
    )
    f.link(db, event, one)
    expired = f.opportunity(
        db, "Expired tender", deadline_at=kigali(2026, 11, 20), status="expired"
    )
    f.link(db, expired, two)
    fit_for(db, ana, strong, word="strong")
    fit_for(db, ana, good, word="good")
    fit_for(db, ana, possible, word="possible")
    fit_for(db, ana, expired, word="strong")
    db.commit()
    return one, two, strong, good, possible, event, expired


def test_fit_is_at_least(db, ana, login):
    _, _, strong, good, possible, event, _ = _catalogue(db, ana)
    c = login(ana.email)
    assert ids(c, fit="strong") == [str(strong.id)]
    assert set(ids(c, fit="good")) == {str(strong.id), str(good.id)}
    assert set(ids(c, fit="possible")) == {
        str(strong.id),
        str(good.id),
        str(possible.id),
    }
    # Events carry no fit word, so any fit filter leaves them out.
    assert str(event.id) not in ids(c, fit="possible")
    assert str(event.id) in ids(c)
    assert c.get("/api/feed", params={"fit": "not-scored"}).status_code == 422
    assert c.get("/api/feed", params={"fit": "80"}).status_code == 422


def test_status_filter(db, ana, login):
    _, _, strong, good, possible, event, expired = _catalogue(db, ana)
    c = login(ana.email)
    # 24 Nov 14:00: within 7 days is closing soon.
    assert set(ids(c, status="closing_soon")) == {
        str(strong.id),
        str(possible.id),
        str(event.id),
    }
    assert ids(c, status="open") == [str(good.id)]
    both = c.get("/api/feed", params=[("status", "open"), ("status", "closing_soon")])
    assert len(both.json()["items"]) == 4
    # An untracked expired item is hard-filtered: never shown.
    assert ids(c, status="expired") == []
    c.put(f"/api/opportunities/{expired.id}/state", json={"state": "saved"})
    assert ids(c, status="expired") == [str(expired.id)]
    assert c.get("/api/feed", params={"status": "closed"}).status_code == 422


def test_filters_combine(db, ana, login):
    one, two, strong, good, possible, event, _ = _catalogue(db, ana)
    c = login(ana.email)
    assert ids(c, stream="tender", fit="good", window=7) == [str(strong.id)]
    assert ids(c, stream="tender", status="open", fit="good") == [str(good.id)]
    assert ids(c, source=str(two.id), fit="possible", status="closing_soon") == [
        str(possible.id)
    ]
    assert ids(c, verification="verified_original", fit="strong", window=7) == [
        str(strong.id)
    ]
    assert ids(c, source=str(one.id), stream="event") == [str(event.id)]
    assert ids(c, stream="funding", fit="strong") == []
    c.put(f"/api/opportunities/{good.id}/state", json={"state": "saved"})
    assert ids(c, state="saved", fit="good", status="open") == [str(good.id)]
    assert ids(c, state="saved", fit="strong") == []


def test_profile_filter_with_fit(db, ana, login):
    one = f.source(db, "One")
    t = f.opportunity(db, "Tender", deadline_at=kigali(2026, 12, 5))
    f.link(db, t, one)
    fit_for(db, ana, t, word="strong", profile="A", value=80)
    b = fit_for(db, ana, t, word="possible", profile="B")
    db.commit()
    c = login(ana.email)
    assert ids(c, fit="strong") == [str(t.id)]
    assert ids(c, profile=str(b.id), fit="good") == []
    assert ids(c, profile=str(b.id), fit="possible") == [str(t.id)]
