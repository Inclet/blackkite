"""GET /api/calendar (docs/api-contract.md section 5)."""

from __future__ import annotations

from blackkite.db.models import UserSourceMute
from tests import factories as f
from tests.factories import kigali
from tests.member_helpers import *
from tests.member_helpers import fit_for

WINDOW = {"from": "2026-11-24", "to": "2026-12-31"}


def _cal(c, **params) -> dict:
    r = c.get("/api/calendar", params={**WINDOW, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _flat(body) -> list[tuple[str, str, str, str | None]]:
    return [
        (d["date"], e["title"], e["kind"], e.get("time"))
        for d in body["days"]
        for e in d["entries"]
    ]


def test_needs_a_session(client):
    assert client.get("/api/calendar", params=WINDOW).status_code == 401


def test_entries_by_kigali_day_with_times(db, ana, login):
    src = f.source(db, "Src")
    # Deadline at 23:30 UTC on 29 Nov is 01:30 on 30 Nov in Kigali.
    t = f.opportunity(
        db,
        "Late tender",
        organisation_short="RTDA",
        deadline_at=kigali(2026, 11, 30, 1, 30),
    )
    dated = f.opportunity(
        db,
        "Date-only tender",
        deadline_at=kigali(2026, 12, 2, 23, 59).replace(second=59),
    )
    one_day = f.opportunity(
        db,
        "Summit",
        stream="event",
        event_start=kigali(2026, 12, 3, 9),
        event_end=kigali(2026, 12, 3, 17),
    )
    multi = f.opportunity(
        db,
        "Expo",
        stream="event",
        event_start=kigali(2026, 12, 5, 0, 0),
        event_end=kigali(2026, 12, 7, 23, 59).replace(second=59),
    )
    for o in (t, dated, one_day, multi):
        f.link(db, o, src)
    fit_for(db, ana, t, dated, word="good")
    db.commit()
    c = login(ana.email)
    body = _cal(c)
    assert _flat(body) == [
        ("2026-11-30", "Late tender", "deadline", "01:30"),
        ("2026-12-02", "Date-only tender", "deadline", None),
        ("2026-12-03", "Summit", "event", "09:00"),
        ("2026-12-05", "Expo", "event_start", None),
        ("2026-12-07", "Expo", "event_end", None),
    ]
    first = body["days"][0]["entries"][0]
    assert first == {
        "id": str(t.id),
        "stream": "tender",
        "title": "Late tender",
        "organisationShort": "RTDA",
        "kind": "deadline",
        "time": "01:30",
        "fit": "good",
        "state": "unseen",
        "provisional": False,
    }
    event = body["days"][2]["entries"][0]
    assert "fit" not in event and "time" in event and "organisationShort" not in event
    assert [k for _, _, k, _ in _flat(_cal(c, kind="deadlines"))] == ["deadline"] * 2
    assert {k for _, _, k, _ in _flat(_cal(c, kind="events"))} == {
        "event",
        "event_start",
        "event_end",
    }
    # Only the part of a multi-day event inside the window.
    part = c.get("/api/calendar", params={"from": "2026-12-06", "to": "2026-12-10"})
    assert _flat(part.json()) == [("2026-12-07", "Expo", "event_end", None)]


def test_window_rules(db, ana, login):
    c = login(ana.email)
    ok = c.get("/api/calendar", params={"from": "2026-12-01", "to": "2027-03-30"})
    assert ok.status_code == 200  # 120 days inclusive
    long = c.get("/api/calendar", params={"from": "2026-12-01", "to": "2027-03-31"})
    assert long.status_code == 422
    assert long.json()["detail"] == "The calendar shows at most 120 days at a time."
    back = c.get("/api/calendar", params={"from": "2026-12-02", "to": "2026-12-01"})
    assert back.status_code == 422
    assert c.get("/api/calendar", params={"from": "2026-12-01"}).status_code == 422
    assert c.get("/api/calendar", params={**WINDOW, "kind": "jobs"}).status_code == 422


def test_same_visibility_and_fit_rules_as_the_feed(db, ana, ben, login):
    src = f.source(db, "Src")
    testing = f.source(db, "Testing", status="testing")
    muted = f.source(db, "Muted")
    d = kigali(2026, 12, 10)
    shown = f.opportunity(db, "Shown", deadline_at=d)
    no_word = f.opportunity(db, "No fit word", deadline_at=d)
    unscored = f.opportunity(db, "Not scored", stream="funding", deadline_at=d)
    hidden = f.opportunity(db, "Testing only", deadline_at=d)
    only_muted = f.opportunity(db, "Only muted", deadline_at=d)
    dismissed = f.opportunity(db, "Dismissed", deadline_at=d)
    saved_low = f.opportunity(db, "Saved low", deadline_at=d)
    mine = f.opportunity(
        db, "Mine", deadline_at=d, visibility="private", owner_user_id=ana.id
    )
    bens = f.opportunity(
        db, "Ben's", deadline_at=d, visibility="private", owner_user_id=ben.id
    )
    for o in (shown, no_word, unscored, dismissed, saved_low):
        f.link(db, o, src)
    f.link(db, hidden, testing)
    f.link(db, only_muted, muted)
    db.add(UserSourceMute(user_id=ana.id, source_id=muted.id))
    fit_for(db, ana, shown, hidden, only_muted, dismissed, word="strong")
    fit_for(db, ana, no_word, saved_low, word=None)
    f.state(db, ana, dismissed, "dismissed")
    f.state(db, ana, saved_low, "saved")
    db.commit()
    c = login(ana.email)
    titles = {t for _, t, _, _ in _flat(_cal(c))}
    assert titles == {"Shown", "Saved low", "Mine"}
    assert {t for _, t, _, _ in _flat(_cal(c, saved="true"))} == {"Saved low"}
    assert bens.id and mine.id


def test_closed_items_only_when_tracked(db, ana, login):
    src = f.source(db, "Src")
    past = kigali(2026, 11, 20)
    tracked = f.opportunity(db, "Tracked", deadline_at=past, status="expired")
    untracked = f.opportunity(db, "Untracked", deadline_at=past, status="expired")
    for o in (tracked, untracked):
        f.link(db, o, src)
        f.score(
            db,
            ana,
            o,
            fit_for(db, ana),
            0,
            hard_filtered="deadline_passed",
            fit_word=None,
        )
    f.state(db, ana, tracked, "done")
    db.commit()
    c = login(ana.email)
    body = c.get("/api/calendar", params={"from": "2026-11-01", "to": "2026-11-30"})
    assert [(t, k) for _, t, k, _ in _flat(body.json())] == [("Tracked", "deadline")]
    entry = body.json()["days"][0]["entries"][0]
    assert entry["state"] == "done" and "fit" not in entry
