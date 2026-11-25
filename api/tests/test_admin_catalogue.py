"""Admin bare catalogue and review (spec 3, 11 M1; Phase 3 note on _review)."""

import pytest
import sqlalchemy as sa

from blackkite.db.models import ChangeEvent, Opportunity
from tests import factories as f
from tests.conftest import make_user, sign_in


@pytest.fixture
def admin(db, client, outbox):
    u = make_user(db, "admin@example.com", role="admin")
    sign_in(client, outbox, u.email)
    return u


REASONS = [
    {"code": "deadline_conflict", "detail": "sources disagree on the deadline"},
    {"code": "date", "detail": "deadline_at: date has no year ('25 November')"},
]


def _seed(db, admin):
    testing = f.source(db, "Testing", status="testing")
    active = f.source(db, "Active", kind="original")
    hidden = f.opportunity(
        db,
        "Testing only",
        needs_review=True,
        evidence={"_review": REASONS, "_trust": "conflict", "title": {"snippet": "x"}},
        deadline_at=f.kigali(2026, 12, 3),
    )
    f.link(db, hidden, testing, "https://t.example/1")
    shown = f.opportunity(db, "Shown")
    f.link(db, shown, active, "https://a.example/1", is_original=True)
    member = make_user(db, "m@example.com")
    f.opportunity(db, "Private", visibility="private", owner_user_id=member.id)
    f.opportunity(db, "Admin private", visibility="private", owner_user_id=admin.id)
    db.commit()
    return hidden, shown


def test_lists_public_items_including_testing_only(db, client, admin):
    _seed(db, admin)
    body = client.get("/admin/catalogue").json()
    assert body["total"] == 2
    first, second = body["items"]
    assert first["title"] == "Testing only"  # needs review first
    assert first["needsReview"] is True and first["memberVisible"] is False
    assert first["reviewReasons"] == REASONS
    assert first["trust"] == "conflict" and first["deadline"] == "2026-12-03"
    assert first["sources"] == [
        {
            "name": "Testing",
            "status": "testing",
            "kind": "publisher",
            "isOriginal": False,
            "url": "https://t.example/1",
        }
    ]
    assert second["title"] == "Shown" and second["memberVisible"] is True
    only = client.get("/admin/catalogue", params={"needsReview": "true"}).json()
    assert [i["title"] for i in only["items"]] == ["Testing only"]


def test_review_clears_flag_and_reasons(db, client, admin):
    hidden, _ = _seed(db, admin)
    r = client.post(f"/admin/catalogue/{hidden.id}/review")
    assert r.status_code == 200
    assert r.json()["needsReview"] is False and r.json()["reviewReasons"] == []
    db.expire_all()
    opp = db.get(Opportunity, hidden.id)
    assert opp.needs_review is False
    assert "_review" not in opp.evidence
    assert opp.evidence["title"] == {"snippet": "x"}  # other evidence kept
    [ce] = db.scalars(
        sa.select(ChangeEvent).where(ChangeEvent.opportunity_id == hidden.id)
    )
    assert ce.field == "needs_review" and ce.old["reasons"] == REASONS
    assert ce.new["reviewed_by"] == str(admin.id)
    # Idempotent.
    assert client.post(f"/admin/catalogue/{hidden.id}/review").status_code == 200
    assert db.scalar(sa.select(sa.func.count()).select_from(ChangeEvent)) == 1


def test_private_items_are_not_reviewable(db, client, admin):
    _seed(db, admin)
    for title in ("Private", "Admin private"):
        opp = db.scalar(sa.select(Opportunity).where(Opportunity.title == title))
        assert client.post(f"/admin/catalogue/{opp.id}/review").status_code == 404


def test_members_get_403_and_anonymous_401(db, client, outbox):
    o = f.opportunity(db, "X")
    db.commit()
    assert client.get("/admin/catalogue").status_code == 401
    assert client.post(f"/admin/catalogue/{o.id}/review").status_code == 401
    make_user(db, "m@example.com")
    sign_in(client, outbox, "m@example.com")
    assert client.get("/admin/catalogue").status_code == 403
    assert client.post(f"/admin/catalogue/{o.id}/review").status_code == 403
