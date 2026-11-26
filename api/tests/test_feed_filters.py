"""Feed filters per spec 8 (docs/api-contract.md section 5): stream, profile,
status, deadline window, fit (at least), source, verification, together."""

from __future__ import annotations

import pytest

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
    assert set(ids(c, fit="strong")) == {str(strong.id), str(event.id)}
    assert set(ids(c, fit="good")) == {str(strong.id), str(good.id), str(event.id)}
    assert set(ids(c, fit="possible")) == {
        str(strong.id),
        str(good.id),
        str(possible.id),
        str(event.id),
    }
    # Events carry no fit word (decision 24): a fit filter leaves them in.
    for word in ("strong", "good", "possible"):
        assert str(event.id) in ids(c, fit=word)
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
    assert ids(
        c, stream="tender", verification="verified_original", fit="strong", window=7
    ) == [str(strong.id)]
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


def _saved(c, opp):
    c.put(f"/api/opportunities/{opp.id}/state", json={"state": "saved"})


@pytest.mark.parametrize("stream", ["tender", "funding"])
def test_fit_narrows_tenders_and_funding(db, ana, login, stream):
    one = f.source(db, "One")
    strong = f.opportunity(db, "Strong", stream=stream, deadline_at=kigali(2026, 12, 5))
    possible = f.opportunity(
        db, "Possible", stream=stream, deadline_at=kigali(2026, 12, 6)
    )
    # Saved with no fit word: in the feed (decision 41), out under a fit filter.
    bare = f.opportunity(db, "No word", stream=stream, deadline_at=kigali(2026, 12, 7))
    for o in (strong, possible, bare):
        f.link(db, o, one)
    fit_for(db, ana, strong, word="strong")
    fit_for(db, ana, possible, word="possible")
    fit_for(db, ana, bare, word=None)
    db.commit()
    c = login(ana.email)
    _saved(c, bare)
    assert set(ids(c)) == {str(strong.id), str(possible.id), str(bare.id)}
    assert ids(c, fit="strong") == [str(strong.id)]
    assert ids(c, fit="good") == [str(strong.id)]
    assert set(ids(c, fit="possible")) == {str(strong.id), str(possible.id)}
    assert ids(c, state="saved", fit="possible") == []


@pytest.mark.parametrize("stream", ["event", "investment"])
def test_fit_leaves_events_and_investments_alone(db, ana, login, stream):
    one = f.source(db, "One", kind="original")
    two = f.source(db, "Two")
    dates = (
        {"event_start": kigali(2026, 11, 29, 9)}
        if stream == "event"
        else {"deadline_at": kigali(2026, 11, 29)}
    )
    near = f.opportunity(
        db, "Near", stream=stream, verification="verified_original", **dates
    )
    f.link(db, near, one, is_original=True)
    far_dates = (
        {"event_start": kigali(2027, 1, 20, 9)}
        if stream == "event"
        else {"deadline_at": kigali(2027, 1, 20)}
    )
    far = f.opportunity(db, "Far", stream=stream, **far_dates)
    f.link(db, far, two)
    tender = f.opportunity(db, "Weak tender", deadline_at=kigali(2026, 12, 5))
    f.link(db, tender, one)
    fit_for(db, ana, tender, word="possible")
    db.commit()
    c = login(ana.email)
    for word in ("strong", "good", "possible"):
        assert set(ids(c, fit=word, stream=stream)) == {str(near.id), str(far.id)}
    assert set(ids(c, fit="strong")) == {str(near.id), str(far.id)}
    # Still subject to the other filters.
    assert ids(c, fit="strong", stream=stream, window=7) == [str(near.id)]
    assert ids(c, fit="good", source=str(two.id)) == [str(far.id)]
    assert ids(c, fit="strong", verification="verified_original") == [str(near.id)]
    assert ids(c, fit="strong", stream="tender") == []


@pytest.mark.parametrize("stream", ["tender", "funding", "event", "investment"])
def test_fit_on_own_private_items(db, ana, login, stream):
    dates = (
        {"event_start": kigali(2026, 12, 3, 9)}
        if stream == "event"
        else {"deadline_at": kigali(2026, 12, 3)}
    )
    bare = f.opportunity(
        db,
        "Mine, no word",
        stream=stream,
        visibility="private",
        owner_user_id=ana.id,
        **dates,
    )
    good = f.opportunity(
        db,
        "Mine, good",
        stream=stream,
        visibility="private",
        owner_user_id=ana.id,
        **dates,
    )
    if stream in ("tender", "funding"):
        fit_for(db, ana, good, word="good")
    db.commit()
    c = login(ana.email)
    assert set(ids(c)) == {str(bare.id), str(good.id)}
    if stream in ("tender", "funding"):
        assert ids(c, fit="possible") == [str(good.id)]
        assert ids(c, fit="good") == [str(good.id)]
        assert ids(c, fit="strong") == []
    else:
        for word in ("strong", "good", "possible"):
            assert set(ids(c, fit=word)) == {str(bare.id), str(good.id)}
