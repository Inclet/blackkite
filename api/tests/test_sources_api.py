"""Source registry: admin CRUD, status graph, promotion gate, health, member sources
page, mutes, suggestions, sandboxed test runs, member visibility (spec 3, 4, 10)."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from blackkite.db.models import (
    SOURCE_STATUSES,
    HttpCache,
    Opportunity,
    OpportunitySource,
    Source,
    SourceRun,
    SourceSuggestion,
    User,
    UserSourceMute,
)
from blackkite.pipeline.visibility import visible_source_link, visible_to
from blackkite.routes.sources import get_preview_client_factory
from blackkite.sources import service
from tests.conftest import make_user, sign_in
from tests.fakes import FakeWeb, make_client

ADMIN = "admin@example.com"
MEMBER = "member@example.com"
OTHER = "other@example.com"
H = "notices.example"

HTML_CONFIG = {
    "list_url": f"https://{H}/tenders",
    "selectors": {"item": "li", "title": "a", "deadline": ".dl"},
}
LIST_HTML = """<ul>
<li><a href="/n/1">Invitation for Bids: cold rooms</a> <span class="dl">30 Nov 2026</span></li>
<li><a href="/n/2">EOI: freight forwarding</a></li>
</ul>"""


def new_client(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def web(app) -> FakeWeb:
    w = FakeWeb()
    w.html(H, "/tenders", LIST_HTML)
    app.dependency_overrides[get_preview_client_factory] = lambda: (
        lambda: make_client(w)
    )
    return w


@pytest.fixture
def admin(app, db, outbox):
    user = make_user(db, ADMIN, role="admin")
    c = sign_in(new_client(app), outbox, ADMIN)
    c.user = user
    return c


@pytest.fixture
def member(app, db, outbox):
    user = make_user(db, MEMBER)
    c = sign_in(new_client(app), outbox, MEMBER)
    c.user = user
    return c


def body(**over):
    b = {
        "name": "Notices Example",
        "home_url": f"https://{H}",
        "publisher": "Example Authority",
        "streams": ["tender"],
        "kind": "original",
        "collector_type": "html_list",
        "config": HTML_CONFIG,
        "rate_limit": 5,
        "access_note": "robots allows /tenders (synthetic test)",
    }
    b.update(over)
    return b


def add_source(db, name="S", status="testing", **kw) -> Source:
    s = Source(
        name=name,
        home_url=f"https://{name.lower()}.example",
        streams=kw.pop("streams", ["tender"]),
        kind=kw.pop("kind", "original"),
        collector_type=kw.pop("collector_type", "html_list"),
        config=kw.pop("config", HTML_CONFIG),
        status=status,
        **kw,
    )
    db.add(s)
    db.commit()
    return s


def add_run(db, source, status="succeeded", found=3, ago_hours=1.0, new=0):
    started = datetime.now(UTC) - timedelta(hours=ago_hours)
    r = SourceRun(
        source_id=source.id,
        status=status,
        items_found=found,
        items_new=new,
        started_at=started,
        finished_at=None if status == "running" else started + timedelta(minutes=1),
        error="boom" if status == "failed" else None,
    )
    db.add(r)
    db.commit()
    return r


def count(db, model) -> int:
    return db.scalar(sa.select(sa.func.count()).select_from(model))


# --- create / edit --------------------------------------------------------------------


def test_admin_creates_source_as_testing(admin, db):
    r = admin.post("/admin/sources", json=body(status="active"))
    assert r.status_code == 422  # status is not settable on create
    r = admin.post("/admin/sources", json=body())
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "testing"
    assert out["added_by"] == str(admin.user.id)
    assert out["health"] == "unknown" and out["promotion_runs"] == 0
    assert out["effective_schedule"] == "0 4 * * *"
    assert out["config"]["selectors"]["title"] == {"css": "a"}
    assert admin.post("/admin/sources", json=body()).status_code == 409


@pytest.mark.parametrize(
    "over",
    [
        {"home_url": "http://169.254.169.254/"},
        {"home_url": "https://u:p@notices.example/"},
        {"config": {**HTML_CONFIG, "list_url": "http://localhost:8000/"}},
        {
            "config": {
                "list_url": f"https://{H}/",
                "selectors": {"item": "[[", "title": "a"},
            }
        },
        {"schedule": "every day"},
        {"schedule": "0 25 * * *"},
        {"streams": []},
        {"streams": ["tender", "tender"]},
        {"streams": ["jobs"]},
        {"kind": "blog"},
        {"collector_type": "selenium"},
        {"rate_limit": 0},
        {"rate_limit": 0.5},
        {"collector_type": "search_query", "config": {"queries": []}},
        # Search results are never the issuer itself.
        {"collector_type": "search_query", "config": {"queries": ["tender"]}},
    ],
)
def test_create_rejects_bad_input(admin, over):
    r = admin.post("/admin/sources", json=body(**over))
    assert r.status_code == 422, r.text


def test_unimplemented_type_config_stored_as_given(admin):
    r = admin.post(
        "/admin/sources",
        json=body(collector_type="rss", config={"feed_url": f"https://{H}/feed"}),
    )
    assert r.status_code == 201 and r.json()["config"] == {
        "feed_url": f"https://{H}/feed"
    }


def test_edit_tracks_config_changes(admin, db):
    sid = admin.post("/admin/sources", json=body()).json()["id"]
    r = admin.patch(f"/admin/sources/{sid}", json={"access_note": "rechecked"})
    assert r.status_code == 200 and r.json()["config_changed_at"] is None
    r = admin.patch(f"/admin/sources/{sid}", json={"config": HTML_CONFIG})
    assert r.json()["config_changed_at"] is None  # same config: not a change
    new_cfg = {**HTML_CONFIG, "max_pages": 2}
    r = admin.patch(f"/admin/sources/{sid}", json={"config": new_cfg})
    assert r.status_code == 200 and r.json()["config_changed_at"] is not None
    assert (
        admin.patch(f"/admin/sources/{sid}", json={"status": "active"}).status_code
        == 422
    )
    bad = admin.patch(
        f"/admin/sources/{sid}", json={"config": {"list_url": "ftp://x/"}}
    )
    assert bad.status_code == 422
    # switching type re-validates the stored config against the new type
    assert (
        admin.patch(
            f"/admin/sources/{sid}", json={"collector_type": "search_query"}
        ).status_code
        == 422
    )
    assert admin.patch(f"/admin/sources/{sid}", json={"name": None}).status_code == 422


def test_member_cannot_manage_sources(member, db):
    s = add_source(db)
    assert member.post("/admin/sources", json=body()).status_code == 403
    assert member.patch(f"/admin/sources/{s.id}", json={"name": "x"}).status_code == 403
    assert (
        member.post(
            f"/admin/sources/{s.id}/status", json={"status": "paused"}
        ).status_code
        == 403
    )
    assert member.post(f"/admin/sources/{s.id}/test-run").status_code == 403


# --- status graph and promotion -----------------------------------------------------------

EXPECTED_EDGES = {
    ("suggested", "testing"),
    ("suggested", "retired"),
    ("testing", "active"),
    ("testing", "paused"),
    ("testing", "retired"),
    ("active", "paused"),
    ("active", "retired"),
    ("active", "testing"),
    ("paused", "active"),
    ("paused", "testing"),
    ("paused", "retired"),
    ("retired", "testing"),
}


@pytest.mark.parametrize(
    ("old", "new"),
    [(a, b) for a, b in itertools.product(SOURCE_STATUSES, repeat=2) if a != b],
)
def test_status_graph(db, old, new):
    s = add_source(db, status=old)
    add_run(db, s)
    add_run(db, s)
    if (old, new) in EXPECTED_EDGES:
        service.change_status(db, s, new)
        assert s.status == new
    else:
        with pytest.raises(service.TransitionError):
            service.change_status(db, s, new)
        db.rollback()


def test_promotion_needs_two_successful_runs_with_items(admin, db):
    s = add_source(db)
    promote = lambda: admin.post(
        f"/admin/sources/{s.id}/status", json={"status": "active"}
    )
    r = promote()
    assert r.status_code == 409 and "has 0" in r.json()["detail"]
    add_run(db, s, "succeeded", found=4, ago_hours=5)
    add_run(db, s, "failed", found=0, ago_hours=4)
    add_run(db, s, "succeeded", found=0, ago_hours=3)  # ran, but found nothing
    add_run(db, s, "running", found=9, ago_hours=0.1)
    assert promote().status_code == 409
    add_run(db, s, "succeeded", found=2, ago_hours=2)
    r = promote()
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


def test_promotion_counts_only_runs_after_config_change(admin, db):
    s = add_source(db)
    add_run(db, s, ago_hours=3)
    add_run(db, s, ago_hours=2)
    admin.patch(
        f"/admin/sources/{s.id}", json={"config": {**HTML_CONFIG, "max_pages": 3}}
    )
    r = admin.post(f"/admin/sources/{s.id}/status", json={"status": "active"})
    assert r.status_code == 409
    db.expire_all()
    s = db.get(Source, s.id)
    r1 = add_run(db, s, ago_hours=0)
    r1.started_at = s.config_changed_at + timedelta(seconds=1)
    r2 = add_run(db, s, ago_hours=0)
    r2.started_at = s.config_changed_at + timedelta(seconds=2)
    db.commit()
    r = admin.post(f"/admin/sources/{s.id}/status", json={"status": "active"})
    assert r.status_code == 200, r.text


def test_pause_retire_and_invalid_transition(admin, db):
    s = add_source(db)
    ok = admin.post(f"/admin/sources/{s.id}/status", json={"status": "paused"})
    assert ok.status_code == 200 and ok.json()["status"] == "paused"
    ok = admin.post(f"/admin/sources/{s.id}/status", json={"status": "retired"})
    assert ok.status_code == 200
    bad = admin.post(f"/admin/sources/{s.id}/status", json={"status": "paused"})
    assert bad.status_code == 409 and "retired to paused" in bad.json()["detail"]
    assert (
        admin.post(f"/admin/sources/{s.id}/status", json={"status": "gone"}).status_code
        == 422
    )


# --- health ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("runs", "health"),
    [
        ([], "unknown"),
        ([("succeeded", 3)], "ok"),
        ([("succeeded", 3), ("succeeded", 1), ("succeeded", 2)], "ok"),
        ([("succeeded", 3), ("succeeded", 1), ("succeeded", 2), ("failed", 0)], "ok"),
        ([("succeeded", 0)], "degraded"),
        ([("succeeded", 3), ("failed", 0)], "degraded"),
        ([("succeeded", 3), ("succeeded", 3), ("failed", 0)], "degraded"),
        ([("failed", 0), ("succeeded", 3)], "degraded"),
        ([("failed", 0)], "failing"),
        ([("failed", 0), ("failed", 0), ("succeeded", 5)], "failing"),
    ],
)
def test_health_rule(runs, health):
    assert service.health_from_runs(runs) == health


def test_health_ignores_running_runs(db):
    s = add_source(db, status="active")
    add_run(db, s, "succeeded", found=2, ago_hours=2)
    add_run(db, s, "running", found=0, ago_hours=0.1)
    assert service.source_stats(db, [s.id])[s.id].health == "ok"


# --- member sources page ------------------------------------------------------------------------


def _carry(db, source, n, *, ago_days=1.0):
    for i in range(n):
        o = Opportunity(stream="tender", title=f"{source.name} item {i}")
        db.add(o)
        db.flush()
        seen = datetime.now(UTC) - timedelta(days=ago_days)
        db.add(
            OpportunitySource(
                opportunity_id=o.id,
                source_id=source.id,
                url=f"https://x.example/{source.name}/{i}/{ago_days}",
                first_seen=seen,
                last_seen=seen,
            )
        )
    db.commit()


def test_members_see_only_active_sources_with_stats(member, db):
    a = add_source(
        db, "Alpha", "active", publisher="Alpha Org", streams=["tender", "event"]
    )
    add_source(db, "Testing", "testing")
    add_source(db, "Paused", "paused")
    add_source(db, "Retired", "retired")
    add_run(db, a, "succeeded", found=5, ago_hours=30)
    add_run(db, a, "failed", found=0, ago_hours=2)
    _carry(db, a, 3, ago_days=2)
    _carry(db, a, 2, ago_days=45)  # outside the 30-day window
    r = member.get("/sources")
    assert r.status_code == 200
    (row,) = r.json()
    assert row["name"] == "Alpha" and row["publisher"] == "Alpha Org"
    assert row["kind"] == "original" and row["streams"] == ["tender", "event"]
    assert row["items_30d"] == 3
    assert row["health"] == "degraded"
    assert row["last_success_at"] is not None and row["muted"] is False
    assert "config" not in row and "access_note" not in row


def test_sources_page_needs_sign_in(app):
    assert new_client(app).get("/sources").status_code == 401


def test_mute_is_per_user(app, member, db, outbox):
    a = add_source(db, "Alpha", "active")
    t = add_source(db, "Hidden", "testing")
    assert member.post(f"/sources/{a.id}/mute").status_code == 204
    assert member.post(f"/sources/{a.id}/mute").status_code == 204  # idempotent
    assert member.post(f"/sources/{t.id}/mute").status_code == 404
    assert member.get("/sources").json()[0]["muted"] is True

    make_user(db, OTHER)
    other = sign_in(new_client(app), outbox, OTHER)
    assert other.get("/sources").json()[0]["muted"] is False

    a.status = "paused"
    db.commit()
    assert member.delete(f"/sources/{a.id}/mute").status_code == 204
    assert count(db, UserSourceMute) == 0


# --- suggestions --------------------------------------------------------------------------------


def test_suggestion_flow(app, admin, member, db, outbox):
    r = member.post(
        "/source-suggestions",
        json={
            "url": "https://calls.example/rw",
            "note": "Monthly grant calls for Rwanda",
        },
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["status"] == "suggested"
    assert (
        member.post("/source-suggestions", json={"url": "http://10.0.0.1/"}).status_code
        == 422
    )
    assert (
        member.post("/source-suggestions", json={"url": "notaurl"}).status_code == 422
    )

    make_user(db, OTHER)
    other = sign_in(new_client(app), outbox, OTHER)
    assert other.get("/source-suggestions").json() == []
    assert [s["id"] for s in member.get("/source-suggestions").json()] == [sid]
    assert member.get("/admin/source-suggestions").status_code == 403

    queue = admin.get("/admin/source-suggestions").json()
    assert [q["id"] for q in queue] == [sid] and queue[0]["user_id"] == str(
        member.user.id
    )

    # Creating from a suggestion that is not accepted yet is refused.
    assert admin.post("/admin/sources", json=body(suggestion_id=sid)).status_code == 409
    r = admin.post(f"/admin/source-suggestions/{sid}/accept")
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "accepted" and out["reviewed_by"] == str(admin.user.id)
    assert out["reviewed_at"] is not None
    assert admin.post(f"/admin/source-suggestions/{sid}/reject").status_code == 409
    assert admin.get("/admin/source-suggestions").json() == []

    created = admin.post("/admin/sources", json=body(suggestion_id=sid))
    assert created.status_code == 201 and created.json()["status"] == "testing"
    db.expire_all()
    assert str(db.get(SourceSuggestion, sid).source_id) == created.json()["id"]
    again = admin.post("/admin/sources", json=body(name="Other", suggestion_id=sid))
    assert again.status_code == 409


def test_reject_suggestion(admin, member):
    sid = member.post("/source-suggestions", json={"url": "https://x.example/"}).json()[
        "id"
    ]
    r = admin.post(f"/admin/source-suggestions/{sid}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert [
        s["id"] for s in admin.get("/admin/source-suggestions?status=rejected").json()
    ] == [sid]


# --- test runs -----------------------------------------------------------------------------------


def test_saved_test_run_previews_and_writes_nothing(admin, db, web, monkeypatch):
    from blackkite.pipeline import ingest

    def forbidden(*a, **kw):
        raise AssertionError("test run called the pipeline")

    monkeypatch.setattr(ingest, "ingest_items", forbidden)
    monkeypatch.setattr(ingest, "default_deps", forbidden)
    s = add_source(db, "Notices", "testing")
    before = (db.get(Source, s.id).updated_at, db.get(Source, s.id).status)
    r = admin.post(f"/admin/sources/{s.id}/test-run")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["error"] is None
    assert [(i["title"], i["url"], i["listed_deadline"]) for i in out["items"]] == [
        ("Invitation for Bids: cold rooms", f"https://{H}/n/1", "30 Nov 2026"),
        ("EOI: freight forwarding", f"https://{H}/n/2", None),
    ]
    assert out["requests_made"] == 2  # robots.txt + list page
    assert count(db, SourceRun) == 0
    assert count(db, Opportunity) == 0 and count(db, OpportunitySource) == 0
    assert count(db, HttpCache) == 0
    db.expire_all()
    assert (db.get(Source, s.id).updated_at, db.get(Source, s.id).status) == before


def test_unsaved_test_run(admin, db, web):
    r = admin.post(
        "/admin/sources/test-run",
        json={"collector_type": "html_list", "config": HTML_CONFIG, "rate_limit": 2},
    )
    assert r.status_code == 200 and r.json()["ok"] and len(r.json()["items"]) == 2
    assert count(db, Source) == 0 and count(db, SourceRun) == 0


def test_test_run_failure_is_reported_not_raised(admin, db, web):
    seed = add_source(db, "Seed", config={"placeholder": True})
    r = admin.post(f"/admin/sources/{seed.id}/test-run").json()
    assert r["ok"] is False and "placeholder" in r["error"]
    rss = add_source(db, "Feed", collector_type="rss", config={"feed_url": "x"})
    r = admin.post(f"/admin/sources/{rss.id}/test-run").json()
    assert r["ok"] is False and "not implemented yet" in r["error"]
    r = admin.post(
        "/admin/sources/test-run",
        json={"collector_type": "search_query", "config": {"queries": ["x"]}},
    ).json()
    assert r["ok"] is False and r["error"] == "no search key configured"
    assert web.requests == []
    assert count(db, SourceRun) == 0


def test_test_run_uses_the_url_guard(app, admin, db):
    """Sandboxed: a hostname that resolves to an internal address is never fetched."""
    w = FakeWeb()
    app.dependency_overrides[get_preview_client_factory] = lambda: (
        lambda: make_client(w, resolver=lambda h, p: ["10.0.0.7"])
    )
    r = admin.post(
        "/admin/sources/test-run",
        json={"collector_type": "html_list", "config": HTML_CONFIG},
    )
    assert r.status_code == 200 and r.json()["ok"] is False
    assert "non-public" in r.json()["error"]
    assert w.requests == []
    r = admin.post(
        "/admin/sources/test-run",
        json={
            "collector_type": "html_list",
            "config": {**HTML_CONFIG, "list_url": "http://[::1]/"},
        },
    )
    assert r.status_code == 422


def test_run_history(admin, db):
    s = add_source(db)
    add_run(db, s, "failed", ago_hours=2)
    add_run(db, s, "succeeded", ago_hours=1, found=7, new=2)
    runs = admin.get(f"/admin/sources/{s.id}/runs").json()
    assert [(r["status"], r["items_found"], r["items_new"]) for r in runs] == [
        ("succeeded", 7, 2),
        ("failed", 3, 0),
    ]
    assert runs[1]["error"] == "boom"
    assert [r["items_failed"] for r in runs] == [0, 0]
    assert admin.get(f"/admin/sources/{s.id}").json()["health"] == "degraded"
    partly = add_run(db, s, "succeeded", ago_hours=0.5, found=4, new=1)
    partly.items_failed = 2
    db.commit()
    latest = admin.get(f"/admin/sources/{s.id}/runs").json()[0]
    assert (latest["items_found"], latest["items_failed"]) == (4, 2)


# --- member visibility of catalogue items -----------------------------------------------------------


# One rule (pipeline/visibility.py): a member sees a public item only while a
# source carrying it is active or paused. Retired is pending the owner's
# confirmation (one-line change to MEMBER_VISIBLE_SOURCE_STATUSES).
MEMBER_SEES = {
    "suggested": False,
    "testing": False,
    "active": True,
    "paused": True,
    "retired": False,
}


def test_visibility_rule_covers_every_source_status():
    assert set(MEMBER_SEES) == set(SOURCE_STATUSES)


@pytest.mark.parametrize("status", sorted(MEMBER_SEES))
def test_member_visibility_by_carrying_source_status(db, status):
    member = make_user(db, MEMBER)
    admin = make_user(db, ADMIN, role="admin")
    src = add_source(db, f"Only {status}", status)
    o = Opportunity(stream="tender", title=f"from {status}")
    db.add(o)
    db.flush()
    db.add(OpportunitySource(opportunity_id=o.id, source_id=src.id, url="https://x/1"))
    db.commit()

    def titles(user, is_admin):
        q = sa.select(Opportunity.title).where(visible_to(user.id, is_admin=is_admin))
        return set(db.scalars(q))

    assert titles(member, False) == (
        {f"from {status}"} if MEMBER_SEES[status] else set()
    )
    assert titles(admin, True) == {f"from {status}"}  # admins see every public item
    links = db.scalars(
        sa.select(Source.name)
        .join(OpportunitySource, OpportunitySource.source_id == Source.id)
        .where(visible_source_link())
    ).all()
    assert links == ([src.name] if MEMBER_SEES[status] else [])


def test_member_visibility_mixed_sources_and_private_items(db):
    owner = make_user(db, MEMBER)
    other = make_user(db, OTHER)
    admin = make_user(db, ADMIN, role="admin")
    active = add_source(db, "Active", "active")
    testing = add_source(db, "Testing", "testing")
    retired = add_source(db, "Retired", "retired")

    def opp(title, sources, **kw):
        o = Opportunity(stream="tender", title=title, **kw)
        db.add(o)
        db.flush()
        for s in sources:
            db.add(
                OpportunitySource(
                    opportunity_id=o.id, source_id=s.id, url=f"https://x/{title}"
                )
            )
        return o

    opp("from active", [active])
    opp("from testing only", [testing])
    opp("from active and testing", [active, testing])
    opp("from testing and retired", [testing, retired])
    opp("no source", [])
    opp("private mine", [], visibility="private", owner_user_id=owner.id)
    opp("private theirs", [], visibility="private", owner_user_id=other.id)
    db.commit()

    def titles(user, is_admin=False):
        q = sa.select(Opportunity.title).where(visible_to(user.id, is_admin=is_admin))
        return set(db.scalars(q))

    assert titles(owner) == {"from active", "from active and testing", "private mine"}
    assert titles(other) == {"from active", "from active and testing", "private theirs"}
    assert "private mine" not in titles(admin, True)
    assert titles(admin, True) >= {"from testing only", "no source"}

    links = (
        db.execute(
            sa.select(Source.name)
            .join(OpportunitySource, OpportunitySource.source_id == Source.id)
            .join(Opportunity, Opportunity.id == OpportunitySource.opportunity_id)
            .where(
                Opportunity.title == "from active and testing", visible_source_link()
            )
        )
        .scalars()
        .all()
    )
    assert links == ["Active"]


def test_original_search_query_is_refused_on_edit(admin, db):
    s = add_source(
        db,
        "Search",
        kind="publisher",
        collector_type="search_query",
        config={"queries": ["tender Rwanda"]},
    )
    r = admin.patch(f"/admin/sources/{s.id}", json={"kind": "original"})
    assert r.status_code == 422 and "search_query" in r.json()["detail"]
    o = add_source(db, "Orig", kind="original")
    r = admin.patch(
        f"/admin/sources/{o.id}",
        json={"collector_type": "search_query", "config": {"queries": ["x"]}},
    )
    assert r.status_code == 422
    ok = admin.patch(
        f"/admin/sources/{o.id}",
        json={
            "kind": "publisher",
            "collector_type": "search_query",
            "config": {"queries": ["x"]},
        },
    )
    assert ok.status_code == 200, ok.text


def _carried_by(db, title, *sources, original=None):
    o = Opportunity(stream="tender", title=title, evidence={})
    db.add(o)
    db.flush()
    for i, src in enumerate(sources):
        db.add(
            OpportunitySource(
                opportunity_id=o.id,
                source_id=src.id,
                url=f"https://x/{title}/{i}",
                is_original=src is original,
            )
        )
    db.commit()
    return o


def test_verification_counts_only_member_visible_sources(admin, db):
    orig = add_source(db, "Issuer", "testing", kind="original")
    agg = add_source(db, "Agg", "active", kind="aggregator")
    o = _carried_by(db, "cold rooms", orig, agg, original=orig)
    service.refresh_verification_for_source(db, orig.id)
    db.commit()
    db.refresh(o)
    # Testing original: members see only the aggregator.
    assert o.verification == "aggregator_only"
    assert o.evidence["_trust"] == "unconfirmed"

    # Promotion through the API recomputes the source's items.
    add_run(db, orig, found=2, ago_hours=3)
    add_run(db, orig, found=2, ago_hours=2)
    r = admin.post(f"/admin/sources/{orig.id}/status", json={"status": "active"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert o.verification == "verified_original"
    assert o.evidence["_trust"] == "confirmed"

    # Paused stays visible (and confirmed); retired no longer counts.
    admin.post(f"/admin/sources/{orig.id}/status", json={"status": "paused"})
    db.expire_all()
    assert o.verification == "verified_original"
    admin.post(f"/admin/sources/{orig.id}/status", json={"status": "retired"})
    db.expire_all()
    assert o.verification == "aggregator_only"
    assert o.evidence["_trust"] == "unconfirmed"


def test_kind_change_recomputes_verification(admin, db):
    src = add_source(db, "Board", "active", kind="original")
    o = _carried_by(db, "freight", src, original=src)
    service.refresh_verification_for_source(db, src.id)
    db.commit()
    db.refresh(o)
    assert o.verification == "verified_original"
    r = admin.patch(f"/admin/sources/{src.id}", json={"kind": "publisher"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert o.verification == "unverified"


def test_config_edit_on_an_active_source_sends_it_back_to_testing(admin, member, db):
    src = add_source(db, "Live", "active", kind="original")
    o = _carried_by(db, "cold rooms live", src, original=src)
    service.refresh_verification_for_source(db, src.id)
    db.commit()
    member_user = db.scalar(sa.select(User).where(User.role == "member"))

    def member_sees():
        db.expire_all()
        q = sa.select(Opportunity.id).where(visible_to(member_user.id, is_admin=False))
        return o.id in set(db.scalars(q))

    assert member_sees()

    # Other fields leave the status alone.
    for change in (
        {"name": "Live renamed"},
        {"publisher": "Example Authority"},
        {"schedule": "0 5 * * *"},
        {"rate_limit": 9},
        {"access_note": "rechecked from the host"},
        {"config": HTML_CONFIG},  # same config: not a change
    ):
        r = admin.patch(f"/admin/sources/{src.id}", json=change)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active", change

    r = admin.patch(
        f"/admin/sources/{src.id}", json={"config": {**HTML_CONFIG, "max_pages": 4}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "testing"
    assert r.json()["promotion_runs"] == 0
    db.expire_all()
    assert o.verification == "unverified"  # nothing member-visible carries it
    assert not member_sees()

    # Promotion needs two good runs since the config change again.
    assert (
        admin.post(f"/admin/sources/{src.id}/status", json={"status": "active"})
    ).status_code == 409


def test_collector_type_edit_on_an_active_source_keeps_items_carried_elsewhere(
    admin, member, db
):
    src = add_source(db, "Feed", "active", kind="original")
    other = add_source(db, "Board2", "paused", kind="publisher")
    o = _carried_by(db, "trucks", src, other, original=src)
    service.refresh_verification_for_source(db, src.id)
    db.commit()
    member_user = db.scalar(sa.select(User).where(User.role == "member"))
    r = admin.patch(
        f"/admin/sources/{src.id}",
        json={
            "collector_type": "rss",
            "config": {"feed_url": "https://feed.example.org/rss"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "testing"
    db.expire_all()
    assert o.verification == "unverified"  # only the paused publisher counts
    q = sa.select(Opportunity.id).where(visible_to(member_user.id, is_admin=False))
    assert o.id in set(db.scalars(q))

    # A paused or testing source keeps its status on a config edit.
    r = admin.patch(
        f"/admin/sources/{other.id}", json={"config": {**HTML_CONFIG, "max_pages": 5}}
    )
    assert r.json()["status"] == "paused"


# --- role checks on every admin source and suggestion route ---------------------------------

SOURCE_ADMIN_PREFIXES = ("/admin/sources", "/admin/source-suggestions")
EXPECTED_SOURCE_ADMIN_ROUTES = {
    ("GET", "/admin/sources"),
    ("POST", "/admin/sources"),
    ("GET", "/admin/sources/{source_id}"),
    ("PATCH", "/admin/sources/{source_id}"),
    ("POST", "/admin/sources/{source_id}/status"),
    ("GET", "/admin/sources/{source_id}/runs"),
    ("POST", "/admin/sources/test-run"),
    ("POST", "/admin/sources/{source_id}/test-run"),
    ("GET", "/admin/source-suggestions"),
    ("POST", "/admin/source-suggestions/{suggestion_id}/accept"),
    ("POST", "/admin/source-suggestions/{suggestion_id}/reject"),
}


def _source_admin_routes(app) -> list[tuple[str, str]]:
    """From OpenAPI, so a new route is covered without editing this test."""
    return sorted(
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith(SOURCE_ADMIN_PREFIXES)
        for method in ops
    )


def _valid_request(method, path, source, suggestion):
    """A request that would succeed for an admin: real ids, valid bodies."""
    url = path.format(source_id=source.id, suggestion_id=suggestion.id)
    payload = None
    if (method, path) == ("POST", "/admin/sources"):
        payload = body(name="Created by a non-admin")
    elif method == "PATCH":
        payload = {"name": "Renamed by a non-admin"}
    elif path.endswith("/status"):
        payload = {"status": "retired"}
    elif path == "/admin/sources/test-run":
        payload = {"collector_type": "html_list", "config": HTML_CONFIG}
    return method, url, payload


def _fixtures_for_routes(db, member_user):
    src = add_source(db, "Guarded")
    sug = SourceSuggestion(user_id=member_user.id, url="https://calls.example/")
    db.add(sug)
    db.commit()
    return src, sug


def _unchanged(db, src, sug):
    db.expire_all()
    assert db.get(Source, src.id).name == "Guarded"
    assert db.get(Source, src.id).status == "testing"
    assert db.get(SourceSuggestion, sug.id).status == "suggested"
    assert count(db, Source) == 1


def test_source_admin_route_list_is_complete(app):
    assert set(_source_admin_routes(app)) >= EXPECTED_SOURCE_ADMIN_ROUTES


def test_every_source_admin_route_needs_sign_in(app, db, web):
    owner = make_user(db, OTHER)
    src, sug = _fixtures_for_routes(db, owner)
    c = new_client(app)
    for method, path in _source_admin_routes(app):
        m, url, payload = _valid_request(method, path, src, sug)
        r = c.request(m, url, json=payload)
        assert r.status_code == 401, (method, path, r.status_code)
    _unchanged(db, src, sug)
    assert web.requests == []  # no test run reached the network


def test_every_source_admin_route_refuses_members(app, member, db, web):
    src, sug = _fixtures_for_routes(db, member.user)
    for method, path in _source_admin_routes(app):
        m, url, payload = _valid_request(method, path, src, sug)
        r = member.request(m, url, json=payload)
        assert r.status_code == 403, (method, path, r.status_code)
    _unchanged(db, src, sug)
    assert web.requests == []


def test_every_source_admin_route_admits_admins(app, admin, db, web):
    """The same requests succeed for an admin, so the 401/403 above are real."""
    member_user = make_user(db, MEMBER)
    src, sug = _fixtures_for_routes(db, member_user)
    for method, path in _source_admin_routes(app):
        if path.endswith("/reject"):
            continue  # accept ran first (sorted order) and used the suggestion
        m, url, payload = _valid_request(method, path, src, sug)
        r = admin.request(m, url, json=payload)
        assert r.status_code < 400, (method, path, r.status_code, r.text)


# --- mutes re-score the caller (spec 7 hard filter muted_source_only) -------------------


def _scored_item(db, member):
    from datetime import UTC, datetime, timedelta

    from tests import factories as f

    src = f.source(db, "Cold Board")
    opp = f.opportunity(
        db,
        "Cold chain transport of vaccines",
        tags=["service:cold chain"],
        deadline_at=datetime.now(UTC) + timedelta(days=20),
        location="Kigali, Rwanda",
    )
    f.link(db, opp, src)
    f.profile(db, member.user, "Cold", services=["cold chain"])
    db.commit()
    return src, opp


def _filtered(db, user, opp):
    from blackkite.db.models import UserOpportunityScore

    db.expire_all()
    rows = db.scalars(
        sa.select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == user.id,
            UserOpportunityScore.opportunity_id == opp.id,
        )
    ).all()
    return [r.score_breakdown["hard_filtered"] for r in rows]


def test_mute_and_unmute_rescore_the_caller(member, db):
    from blackkite import scoring

    src, opp = _scored_item(db, member)
    scoring.score_user(db, member.user.id)
    db.commit()
    assert _filtered(db, member.user, opp) == [None]

    assert member.post(f"/sources/{src.id}/mute").status_code == 204
    assert _filtered(db, member.user, opp) == ["muted_source_only"]
    assert member.get("/api/feed").json()["items"] == []

    assert member.delete(f"/sources/{src.id}/mute").status_code == 204
    assert _filtered(db, member.user, opp) == [None]
    assert [i["id"] for i in member.get("/api/feed").json()["items"]] == [str(opp.id)]


def test_mute_rescores_only_the_caller(app, member, db, outbox, monkeypatch):
    from blackkite import scoring

    calls = []
    monkeypatch.setattr(scoring, "score_user", lambda s, uid: calls.append(uid))
    a = add_source(db, "Alpha", "active")
    member.post(f"/sources/{a.id}/mute")
    member.delete(f"/sources/{a.id}/mute")
    assert calls == [member.user.id, member.user.id]


def test_rescoring_failure_keeps_the_mute(member, db, monkeypatch, caplog):
    from blackkite import scoring

    def broken(session, user_id):
        session.execute(sa.text("SELECT 1"))
        raise RuntimeError("scoring blew up")

    monkeypatch.setattr(scoring, "score_user", broken)
    a = add_source(db, "Alpha", "active")
    with caplog.at_level("ERROR", logger="blackkite.sources"):
        assert member.post(f"/sources/{a.id}/mute").status_code == 204
    assert count(db, UserSourceMute) == 1
    assert "re-scoring after a mute change failed" in caplog.text
    with caplog.at_level("ERROR", logger="blackkite.sources"):
        assert member.delete(f"/sources/{a.id}/mute").status_code == 204
    assert count(db, UserSourceMute) == 0
