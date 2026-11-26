"""Personal calendar feed: GET /api/calendar.ics?token=..., feed-link and rotate
(docs/api-contract.md section 5). The output is checked with an independent
RFC 5545 parser (icalendar) as well as line by line."""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlsplit

import icalendar
from fastapi.testclient import TestClient

from blackkite.auth.ratelimit import SlidingWindowLimiter
from blackkite.db.models import User, UserOpportunity
from blackkite.member import ics
from tests import factories as f
from tests.factories import kigali
from tests.member_helpers import *
from tests.member_helpers import fit_for


def _token(c: TestClient) -> str:
    r = c.get("/api/calendar/feed-link")
    assert r.status_code == 200, r.text
    body = r.json()
    url = body["url"]
    assert url.startswith("https://testserver/api/calendar.ics?token=")
    assert body["webcalUrl"] == "webcal://" + url.removeprefix("https://")
    return parse_qs(urlsplit(url).query)["token"][0]


def _ics(client: TestClient, token: str):
    return client.get("/api/calendar.ics", params={"token": token})


def _parse(text: str) -> icalendar.Calendar:
    return icalendar.Calendar.from_ical(text)


def _events(cal) -> dict[str, icalendar.Event]:
    return {str(e["UID"]): e for e in cal.walk("VEVENT")}


def _setup(db, ana):
    src = f.source(db, "Src")
    timed = f.opportunity(
        db,
        "Fuel supply, Lot 2; Kigali\\Huye",
        organisation="Rwanda Transport, Development Agency",
        deadline_at=kigali(2026, 12, 4, 10, 0),
    )
    dated = f.opportunity(
        db,
        "Date only",
        deadline_at=kigali(2026, 12, 9, 23, 59).replace(second=59),
    )
    summit = f.opportunity(
        db,
        "Summit",
        stream="event",
        organisation="Org",
        event_start=kigali(2026, 12, 3, 9),
        event_end=kigali(2026, 12, 3, 17),
    )
    expo = f.opportunity(
        db,
        "Expo",
        stream="event",
        event_start=kigali(2026, 12, 5, 0, 0),
        event_end=kigali(2026, 12, 7, 23, 59).replace(second=59),
    )
    unsaved = f.opportunity(db, "Not saved", deadline_at=kigali(2026, 12, 4))
    done = f.opportunity(db, "Done", deadline_at=kigali(2026, 12, 4))
    for o in (timed, dated, summit, expo, unsaved, done):
        f.link(db, o, src)
    fit_for(db, ana, timed, word="strong", profile="Ironji secret profile")
    f.state(db, ana, timed, "saved", note="private note: call Jean")
    f.state(db, ana, dated, "acting")
    f.state(db, ana, summit, "saved")
    f.state(db, ana, expo, "saved")
    f.state(db, ana, done, "done")
    db.commit()
    return timed, dated, summit, expo


def test_feed_link_needs_a_session(client):
    assert client.get("/api/calendar/feed-link").status_code == 401
    assert client.post("/api/calendar/feed-link/rotate").status_code == 401


def test_feed_content_parses_and_holds_only_what_it_may(db, ana, login, client):
    timed, dated, summit, expo = _setup(db, ana)
    c = login(ana.email)
    token = _token(c)
    assert _token(c) == token  # stable until rotated
    r = _ics(client, token)  # no session
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/calendar; charset=utf-8"
    assert r.headers["cache-control"] == "no-store"
    text = r.text
    for secret in ("private note", "Ironji secret profile", "strong", "Strong"):
        assert secret not in text
    cal = _parse(text)
    assert str(cal["VERSION"]) == "2.0"
    assert [str(t["TZID"]) for t in cal.walk("VTIMEZONE")] == ["Africa/Kigali"]
    evs = _events(cal)
    assert set(evs) == {
        f"{timed.id}-deadline@blackkite",
        f"{dated.id}-deadline@blackkite",
        f"{summit.id}-event@blackkite",
        f"{expo.id}-event@blackkite",
    }
    t = evs[f"{timed.id}-deadline@blackkite"]
    assert str(t["SUMMARY"]) == "Closes: Fuel supply, Lot 2; Kigali\\Huye"
    assert t.decoded("DTSTART") == timed.deadline_at
    assert str(t["DTSTART"].params["TZID"]) == "Africa/Kigali"
    assert "DTEND" not in t
    assert str(t["DESCRIPTION"]) == (
        f"Rwanda Transport, Development Agency\nhttps://testserver/o/{timed.id}"
    )
    assert str(t["URL"]) == f"https://testserver/o/{timed.id}"
    assert t.decoded("DTSTAMP").tzinfo is not None
    d = evs[f"{dated.id}-deadline@blackkite"]
    assert d.decoded("DTSTART") == date(2026, 12, 9)
    assert d.decoded("DTEND") == date(2026, 12, 10)
    s = evs[f"{summit.id}-event@blackkite"]
    assert str(s["SUMMARY"]) == "Summit"
    assert s.decoded("DTSTART") == summit.event_start
    assert s.decoded("DTEND") == summit.event_end
    e = evs[f"{expo.id}-event@blackkite"]
    assert e.decoded("DTSTART") == date(2026, 12, 5)
    assert e.decoded("DTEND") == date(2026, 12, 8)  # exclusive
    # Raw form: CRLF lines, escaped text, folded at 75 octets.
    assert "SUMMARY:Closes: Fuel supply\\, Lot 2\\; Kigali\\\\Huye\r\n" in text
    assert "DTSTART;TZID=Africa/Kigali:20261204T100000\r\n" in text
    assert text.endswith("END:VCALENDAR\r\n")
    for line in text.split("\r\n"):
        assert len(line.encode()) <= 75


def test_long_text_folds_without_splitting_characters():
    line = "SUMMARY:" + "Kigali é ✓ " * 30
    folded = ics.fold(line)
    parts = folded.split("\r\n")
    assert all(len(p.encode()) <= 75 for p in parts)
    assert all(p.startswith(" ") for p in parts[1:])
    assert "".join([parts[0], *(p[1:] for p in parts[1:])]) == line
    assert ics.escape_text("a\r\nb\x07c,d;e\\") == "a\\nbc\\,d\\;e\\\\"


def test_long_unicode_title_round_trips(db, ana, login, client):
    src = f.source(db, "Src")
    title = "Isoko ry’imbuto — " * 8 + "\nsecond line"
    o = f.opportunity(db, title, deadline_at=kigali(2026, 12, 4))
    f.link(db, o, src)
    f.state(db, ana, o, "saved")
    db.commit()
    c = login(ana.email)
    cal = _parse(_ics(client, _token(c)).text)
    (ev,) = cal.walk("VEVENT")
    assert str(ev["SUMMARY"]) == f"Closes: {title}"


def test_rotate_revokes_the_old_link(db, ana, login, client):
    c = login(ana.email)
    old = _token(c)
    assert c.get("/api/calendar/feed-link").json()["rotatedAt"] is None
    r = c.post("/api/calendar/feed-link/rotate")
    assert r.status_code == 200
    assert r.json()["rotatedAt"] is not None
    new = _token(c)
    assert new != old
    assert _ics(client, old).status_code == 404
    assert _ics(client, new).status_code == 200
    # The unsubscribe nonce is untouched.
    before = db.get(User, ana.id).unsubscribe_nonce
    db.expire_all()
    assert db.get(User, ana.id).unsubscribe_nonce == before


def test_bad_tokens_and_deactivated_users(db, ana, login, client):
    c = login(ana.email)
    token = _token(c)
    assert _ics(client, "").status_code == 404
    assert _ics(client, "x" * 66).status_code == 404
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    assert _ics(client, tampered).status_code == 404
    u = db.get(User, ana.id)
    u.status = "deactivated"
    db.commit()
    assert _ics(client, token).status_code == 404


def test_never_includes_another_users_private_item(db, ana, ben, login, client):
    theirs = f.opportunity(
        db,
        "Ben's private",
        deadline_at=kigali(2026, 12, 4),
        visibility="private",
        owner_user_id=ben.id,
    )
    mine = f.opportunity(
        db,
        "Mine",
        deadline_at=kigali(2026, 12, 4),
        visibility="private",
        owner_user_id=ana.id,
    )
    # Even a stray state row on Ben's item must not put it in Ana's feed.
    db.add(UserOpportunity(user_id=ana.id, opportunity_id=theirs.id, state="saved"))
    f.state(db, ana, mine, "saved")
    db.commit()
    c = login(ana.email)
    text = _ics(client, _token(c)).text
    assert "Mine" in text and "Ben" not in text


def test_not_set_up_without_a_secret(settings, ana, login, client):
    c = login(ana.email)
    token = _token(c)
    settings.calendar_secret = None
    assert c.get("/api/calendar/feed-link").status_code == 503
    assert c.post("/api/calendar/feed-link/rotate").status_code == 503
    assert _ics(client, token).status_code == 404


def test_rate_limited_per_token(app, ana, login, client):
    app.state.calendar_limiter = SlidingWindowLimiter(2)
    c = login(ana.email)
    token = _token(c)
    assert _ics(client, token).status_code == 200
    assert _ics(client, token).status_code == 200
    assert _ics(client, token).status_code == 429
    # Another link is counted on its own.
    assert _ics(client, "y" * 66).status_code == 404
