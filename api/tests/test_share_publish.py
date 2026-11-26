"""Share consent and publishing a private item (spec 6; docs/api-contract.md
section 5): PUT /api/items/{id}/share-consent, POST
/api/admin/catalogue/{id}/publish, GET /api/admin/catalogue?shareable=true."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from blackkite.db.models import ChangeEvent, Opportunity, UserOpportunityScore
from blackkite.worker.item_scores import run_pending_item_scores
from tests import factories as f
from tests.conftest import make_user
from tests.member_helpers import *
from tests.member_helpers import items


def _item(c, **kw) -> str:
    body = {
        "stream": "tender",
        "title": "Word-of-mouth tender",
        "deadline": "15 Dec 2026",
    }
    r = c.post("/api/items", json={**body, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _consent(c, oid, allow: bool):
    return c.put(f"/api/items/{oid}/share-consent", json={"allow": allow})


def test_consent_is_owner_only(db, ana, ben, login):
    make_user(db, "admin@example.com", role="admin")
    a = login(ana.email)
    oid = _item(a)
    detail = a.get(f"/api/opportunities/{oid}").json()["detail"]
    assert detail["ownItem"] == {"shareConsent": False, "published": False}
    r = _consent(a, oid, True)
    assert r.status_code == 200 and r.json() == {"allow": True, "published": False}
    assert a.get(f"/api/opportunities/{oid}").json()["detail"]["ownItem"] == {
        "shareConsent": True,
        "published": False,
    }
    assert _consent(login(ben.email), oid, False).status_code == 404
    assert _consent(login("admin@example.com"), oid, True).status_code == 404
    assert _consent(a, oid, False).json() == {"allow": False, "published": False}
    assert a.put(f"/api/items/{oid}/share-consent", json={}).status_code == 422


def test_shareable_list_shows_only_consented_items(db, ana, ben, login):
    make_user(db, "admin@example.com", role="admin")
    a = login(ana.email)
    shared = _item(a, title="Shared", url="https://example.org/n", notes="secret note")
    _item(a, title="Not shared")
    _item(login(ben.email), title="Ben's")
    _consent(a, shared, True)
    admin = login("admin@example.com")
    page = admin.get("/api/admin/catalogue", params={"shareable": "true"}).json()
    assert page["total"] == 1
    (it,) = page["items"]
    assert it["id"] == shared and it["visibility"] == "private"
    assert it["shareConsentAt"] and "madePublicAt" not in it
    assert it["url"] == "https://example.org/n"
    assert "secret note" not in str(page) and ana.email not in str(page)
    # The normal catalogue still lists public items only.
    assert admin.get("/api/admin/catalogue").json()["total"] == 0
    assert login(ana.email).get("/api/admin/catalogue").status_code == 403


def test_publish_needs_consent_and_records_who_and_when(db, ana, ben, login):
    admin_user = make_user(db, "admin@example.com", role="admin")
    a = login(ana.email)
    oid = _item(a)
    admin = login("admin@example.com")
    r = admin.post(f"/api/admin/catalogue/{oid}/publish")
    assert r.status_code == 409
    assert "not agreed" in r.json()["detail"]
    _consent(a, oid, True)
    r = admin.post(f"/api/admin/catalogue/{oid}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["visibility"] == "public" and r.json()["memberVisible"] is True
    db.expire_all()
    opp = db.get(Opportunity, uuid.UUID(oid))
    assert opp.visibility == "public"
    assert opp.owner_user_id == ana.id  # attribution only
    assert opp.made_public_by == admin_user.id and opp.made_public_at is not None
    assert opp.score_requested_at is not None
    ce = db.scalar(
        sa.select(ChangeEvent).where(
            ChangeEvent.opportunity_id == opp.id, ChangeEvent.field == "visibility"
        )
    )
    assert ce.old == {"visibility": "private"}
    assert ce.new == {"visibility": "public", "published_by": str(admin_user.id)}
    # Publishing again changes nothing.
    assert admin.post(f"/api/admin/catalogue/{oid}/publish").status_code == 200
    assert (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(ChangeEvent)
            .where(
                ChangeEvent.opportunity_id == opp.id, ChangeEvent.field == "visibility"
            )
        )
        == 1
    )
    # Ben can see it now; the change history names no admin.
    b = login(ben.email)
    detail = b.get(f"/api/opportunities/{oid}")
    assert detail.status_code == 200
    d = detail.json()["detail"]
    assert "ownItem" not in d
    assert str(admin_user.id) not in str(d["changes"])
    assert d["trust"]["state"] == "unconfirmed"
    assert not d["trust"]["desktop"].startswith("You added")


def test_owner_cannot_withdraw_edit_or_delete_after_publishing(db, ana, login):
    make_user(db, "admin@example.com", role="admin")
    a = login(ana.email)
    oid = _item(a)
    _consent(a, oid, True)
    login("admin@example.com").post(f"/api/admin/catalogue/{oid}/publish")
    r = _consent(a, oid, False)
    assert r.status_code == 409
    assert r.json()["detail"].startswith("This item is public now, so sharing")
    assert _consent(a, oid, True).json() == {"allow": True, "published": True}
    assert a.patch(f"/api/items/{oid}", json={"title": "x"}).status_code == 409
    assert a.delete(f"/api/items/{oid}").status_code == 409
    assert a.get(f"/api/opportunities/{oid}").json()["detail"]["ownItem"] == {
        "shareConsent": True,
        "published": True,
    }


def test_publish_refuses_collected_items_and_unknown_ids(db, login):
    make_user(db, "admin@example.com", role="admin")
    src = f.source(db, "Src")
    pub = f.opportunity(db, "Collected")
    f.link(db, pub, src)
    db.commit()
    admin = login("admin@example.com")
    assert admin.post(f"/api/admin/catalogue/{pub.id}/publish").status_code == 409
    assert admin.post(f"/api/admin/catalogue/{uuid.uuid4()}/publish").status_code == 404


def test_members_cannot_publish(db, ana, login):
    a = login(ana.email)
    oid = _item(a)
    _consent(a, oid, True)
    assert a.post(f"/api/admin/catalogue/{oid}/publish").status_code == 403


def test_published_item_is_scored_for_everyone_and_shows_in_feeds(
    Sessions, db, ana, ben, login
):
    make_user(db, "admin@example.com", role="admin")
    f.profile(db, ana, "Ana's")
    f.profile(db, ben, "Ben's")
    db.commit()
    a = login(ana.email)
    oid = uuid.UUID(_item(a))
    run_pending_item_scores(Sessions, lambda: datetime.now(UTC))
    scored = lambda: set(
        db.scalars(
            sa.select(UserOpportunityScore.user_id).where(
                UserOpportunityScore.opportunity_id == oid
            )
        )
    )
    assert scored() == {ana.id}
    _consent(a, oid, True)
    login("admin@example.com").post(f"/api/admin/catalogue/{oid}/publish")
    assert run_pending_item_scores(Sessions, lambda: datetime.now(UTC)) == [oid]
    db.expire_all()
    assert ben.id in scored() and ana.id in scored()
    # Ben's feed shows it once it has a fit word for him (decision 41).
    b = login(ben.email)
    row = db.scalar(
        sa.select(UserOpportunityScore).where(
            UserOpportunityScore.opportunity_id == oid,
            UserOpportunityScore.user_id == ben.id,
        )
    )
    row.score_breakdown = {
        **(row.score_breakdown or {}),
        "fit_word": "good",
        "hard_filtered": None,
    }
    db.commit()
    assert str(oid) in [i["id"] for i in items(b)]
