"""Private manual items: POST/PATCH/DELETE /api/items (spec 6,
docs/api-contract.md section 5), and the worker queue that scores them for
their owner only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from blackkite.db.models import (
    ChangeEvent,
    Opportunity,
    UserOpportunity,
    UserOpportunityScore,
)
from blackkite.worker.item_scores import run_pending_item_scores
from tests import factories as f
from tests.conftest import make_user
from tests.factories import NOW, kigali
from tests.member_helpers import *
from tests.member_helpers import items

BASIC = {
    "stream": "tender",
    "title": "Cold-chain transport for Musanze cooperative",
    "organisation": "Musanze Dairy Cooperative",
    "deadline": "15 Dec 2026",
    "value": 12000000,
    "currency": "rwf",
    "location": "Musanze",
    "url": "https://example.org/notice",
    "notes": "Heard about it from Jean.",
}


def _create(c, **body) -> dict:
    r = c.post("/api/items", json={**BASIC, **body})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/items"),
        ("patch", f"/api/items/{uuid.uuid4()}"),
        ("delete", f"/api/items/{uuid.uuid4()}"),
    ],
)
def test_needs_a_session(client, method, path):
    kw = {"json": BASIC} if method != "delete" else {}
    assert getattr(client, method)(path, **kw).status_code == 401


def test_create_returns_the_item_and_only_the_owner_sees_it(db, ana, ben, login):
    c = login(ana.email)
    item = _create(c)
    assert item["stream"] == "tender"
    assert item["title"] == BASIC["title"]
    assert item["organisation"] == "Musanze Dairy Cooperative"
    assert item["deadline"] == "2026-12-15"
    assert item["fit"] == "not-scored"
    assert item["state"] == "unseen"
    d = item["detail"]
    assert d["note"] == "Heard about it from Jean."
    assert d["originalUrl"] == "https://example.org/notice"
    assert d["trust"]["state"] == "unconfirmed"
    assert d["trust"]["desktop"].startswith("You added this item yourself")
    assert d["sources"] == []
    fields = {x["name"]: x["value"] for x in d["fields"]}
    assert fields["valueCurrency"] == "RWF"
    assert fields["location"] == "Musanze"

    opp = db.get(Opportunity, uuid.UUID(item["id"]))
    assert (opp.visibility, opp.owner_user_id, opp.verification) == (
        "private",
        ana.id,
        "unverified",
    )
    assert opp.deadline_at == kigali(2026, 12, 15, 23, 59).replace(second=59)
    assert opp.score_requested_at is not None
    assert [i["id"] for i in items(c)] == [item["id"]]
    # Ben: not in his feed, 404 everywhere.
    b = login(ben.email)
    assert items(b) == []
    assert b.get(f"/api/opportunities/{item['id']}").status_code == 404
    assert b.patch(f"/api/items/{item['id']}", json={"title": "x"}).status_code == 404
    assert b.delete(f"/api/items/{item['id']}").status_code == 404


def test_admins_cannot_touch_another_users_item(db, ana, login):
    make_user(db, "admin@example.com", role="admin")
    item = _create(login(ana.email))
    a = login("admin@example.com")
    assert a.get(f"/api/opportunities/{item['id']}").status_code == 404
    assert a.patch(f"/api/items/{item['id']}", json={"title": "x"}).status_code == 404
    assert a.delete(f"/api/items/{item['id']}").status_code == 404
    assert db.get(Opportunity, uuid.UUID(item["id"])) is not None


def test_public_items_are_not_items(db, ana, login):
    src = f.source(db, "Src")
    pub = f.opportunity(db, "Public")
    f.link(db, pub, src)
    db.commit()
    c = login(ana.email)
    assert c.patch(f"/api/items/{pub.id}", json={"title": "x"}).status_code == 404
    assert c.delete(f"/api/items/{pub.id}").status_code == 404


@pytest.mark.parametrize(
    ("body", "detail", "field"),
    [
        (
            {"deadline": "15 December"},
            "Deadline: include the year, for example 30 Nov 2026.",
            "deadline",
        ),
        (
            {"deadline": "next Friday"},
            "Deadline: is not a date we understand; write it like 30 Nov 2026.",
            "deadline",
        ),
        (
            {"deadline": "15 Dec 2031"},
            "Deadline: must be between a year ago and two years from now.",
            "deadline",
        ),
        (
            {"eventStart": "1 Dec 2026"},
            "Event start: only events have event dates.",
            "eventStart",
        ),
        (
            {"url": "javascript:alert(1)"},
            "URL: must be a web address starting with http:// or https://.",
            "url",
        ),
        (
            {"url": "ftp://example.org/x"},
            "URL: must be a web address starting with http:// or https://.",
            "url",
        ),
        ({"title": "  "}, "Title: must not be empty.", "title"),
        ({"currency": "RWFX"}, None, "currency"),
        ({"value": -1}, "Value: must be at least 0.", "value"),
        ({"surprise": 1}, "Surprise: is not a setting this accepts.", "surprise"),
    ],
)
def test_refusals_in_plain_words(db, ana, login, body, detail, field):
    c = login(ana.email)
    r = c.post("/api/items", json={**BASIC, **body})
    assert r.status_code == 422, r.text
    out = r.json()
    if detail:
        assert out["detail"] == detail
    assert [e["field"] for e in out["errors"]] == [field]
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 0


def test_event_dates(db, ana, login):
    c = login(ana.email)
    base = {"stream": "event", "title": "Meetup", "deadline": None}
    ok = c.post(
        "/api/items",
        json={**base, "eventStart": "2026-12-03 18:00", "eventEnd": "3 Dec 2026"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["eventDates"] == {"start": "2026-12-03", "end": "2026-12-03"}
    opp = db.get(Opportunity, uuid.UUID(ok.json()["id"]))
    assert opp.event_start == kigali(2026, 12, 3, 18)
    back = c.post(
        "/api/items",
        json={**base, "eventStart": "5 Dec 2026", "eventEnd": "4 Dec 2026"},
    )
    assert back.status_code == 422
    assert back.json()["detail"] == "Event end: is before the event start."
    alone = c.post("/api/items", json={**base, "eventEnd": "4 Dec 2026"})
    assert alone.json()["errors"][0]["field"] == "eventStart"


def test_patch_edits_records_changes_and_queues_scoring(db, ana, login):
    c = login(ana.email)
    item = _create(c)
    oid = uuid.UUID(item["id"])
    db.execute(
        sa.update(Opportunity)
        .where(Opportunity.id == oid)
        .values(score_requested_at=None)
    )
    db.commit()
    r = c.patch(
        f"/api/items/{oid}",
        json={"deadline": "27 Nov 2026 17:00", "organisation": None, "notes": "Call"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deadline"] == "2026-11-27"
    assert body["organisation"] == ""
    assert body["detail"]["note"] == "Call"
    db.expire_all()
    opp = db.get(Opportunity, oid)
    assert opp.status == "closing_soon"
    assert opp.organisation is None
    assert opp.score_requested_at is not None
    changed = set(
        db.scalars(
            sa.select(ChangeEvent.field).where(ChangeEvent.opportunity_id == oid)
        )
    )
    assert changed == {"deadline_at", "organisation"}
    # A note alone queues nothing and records no change.
    db.execute(
        sa.update(Opportunity)
        .where(Opportunity.id == oid)
        .values(score_requested_at=None)
    )
    db.commit()
    assert c.patch(f"/api/items/{oid}", json={"notes": "x"}).status_code == 200
    db.expire_all()
    assert db.get(Opportunity, oid).score_requested_at is None
    # Refusals change nothing.
    bad = c.patch(f"/api/items/{oid}", json={"title": None})
    assert bad.status_code == 422
    assert bad.json()["detail"] == "Title: cannot be cleared."
    assert (
        c.patch(f"/api/items/{oid}", json={"eventStart": "1 Dec 2026"}).status_code
        == 422
    )
    switch = c.patch(
        f"/api/items/{oid}", json={"stream": "event", "eventStart": "1 Dec 2026"}
    )
    assert switch.status_code == 200, switch.text


def test_delete_removes_the_item_and_its_per_user_rows(db, ana, login):
    c = login(ana.email)
    item = _create(c)
    oid = uuid.UUID(item["id"])
    prof = f.profile(db, ana, "P")
    opp = db.get(Opportunity, oid)
    f.score(db, ana, opp, prof, 60, fit_word="good")
    db.commit()
    assert (
        c.put(f"/api/opportunities/{oid}/state", json={"state": "saved"}).status_code
        == 200
    )
    assert c.delete(f"/api/items/{oid}").status_code == 204
    db.expire_all()
    assert db.get(Opportunity, oid) is None
    for table in (UserOpportunity, UserOpportunityScore):
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(table)
                .where(table.opportunity_id == oid)
            )
            == 0
        )
    assert c.delete(f"/api/items/{oid}").status_code == 404


def test_worker_scores_a_private_item_for_its_owner_only(Sessions, db, ana, ben, login):
    f.profile(db, ana, "Ana's")
    f.profile(db, ben, "Ben's")
    admin = make_user(db, "admin@example.com", role="admin")
    f.profile(db, admin, "Admin's")
    db.commit()
    item = _create(login(ana.email))
    oid = uuid.UUID(item["id"])
    at = datetime.now(UTC)
    assert run_pending_item_scores(Sessions, lambda: at) == [oid]
    owners = set(
        db.scalars(
            sa.select(UserOpportunityScore.user_id).where(
                UserOpportunityScore.opportunity_id == oid
            )
        )
    )
    assert owners == {ana.id}
    db.expire_all()
    assert db.get(Opportunity, oid).score_requested_at is None
    assert run_pending_item_scores(Sessions, lambda: at) == []


def test_worker_leaves_a_newer_request_queued(Sessions, db, ana, login, monkeypatch):
    from blackkite.scoring import service

    f.profile(db, ana, "Ana's")
    db.commit()
    item = _create(login(ana.email))
    oid = uuid.UUID(item["id"])
    real = service.score_opportunities

    def edited_meanwhile(session, ids, **kw):
        out = real(session, ids, **kw)
        with Sessions() as other:
            other.execute(
                sa.update(Opportunity)
                .where(Opportunity.id == oid)
                .values(score_requested_at=NOW.replace(year=2030))
            )
            other.commit()
        return out

    monkeypatch.setattr(service, "score_opportunities", edited_meanwhile)
    run_pending_item_scores(Sessions)
    db.expire_all()
    assert db.get(Opportunity, oid).score_requested_at is not None
