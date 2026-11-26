"""`bk demo-seed`: fictional demo catalogue, dev only, rules-only scores."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from blackkite.db.models import (
    Opportunity,
    OpportunitySource,
    Profile,
    Source,
    SourceRun,
    UserOpportunityScore,
)
from blackkite.delivery.build import build_digest
from blackkite.member.view import load_rows
from blackkite.seed.demo import DEMO_ITEMS, DemoRefused, demo_seed
from blackkite.sources.service import source_stats
from tests import factories as f
from tests.conftest import TEST_UNSUBSCRIBE_SECRET, make_user

ADMIN = "owner@example.com"
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)


def count(db, model, *where):
    return db.scalar(sa.select(sa.func.count()).select_from(model).where(*where))


def test_demo_seed_leaves_no_backfill_for_the_worker(db, Sessions):
    from blackkite.worker.backfills import run_pending_backfills

    demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    profiles = db.scalars(sa.select(Profile)).all()
    assert len(profiles) == 3
    assert all(p.backfill_requested_at is None for p in profiles)

    def fail(*a, **k):
        raise AssertionError("the worker repeated the demo scoring")

    assert run_pending_backfills(Sessions, deps=fail) == []


def test_refuses_outside_dev(db):
    with pytest.raises(DemoRefused, match="BK_ENV is 'prod'"):
        demo_seed(db, env="prod", admin_email=ADMIN, now=NOW)
    assert count(db, Opportunity) == 0


def test_refuses_over_real_opportunities(db):
    src = f.source(db, "Real")
    f.link(db, f.opportunity(db, "A real notice"), src)
    db.commit()
    with pytest.raises(DemoRefused, match="1 non-demo opportunity"):
        demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)


def test_refuses_without_admin_email(db):
    with pytest.raises(DemoRefused, match="BK_FIRST_ADMIN_EMAIL"):
        demo_seed(db, env="dev", admin_email=None, now=NOW)


def test_refuses_a_special_use_admin_email(db):
    with pytest.raises(DemoRefused, match=r"special-use domain \.test"):
        demo_seed(db, env="dev", admin_email="owner@demo.test", now=NOW)
    with pytest.raises(DemoRefused, match="not a valid email address"):
        demo_seed(db, env="dev", admin_email="owner", now=NOW)


def test_loads_a_fictional_catalogue_and_scores_it(db, settings):
    r = demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    opps = db.scalars(sa.select(Opportunity)).all()
    assert len(opps) == r.items == len(DEMO_ITEMS) == 10
    assert Counter(o.stream for o in opps) == {
        "tender": 4,
        "funding": 2,
        "investment": 2,
        "event": 2,
    }
    for o in opps:
        assert o.title.startswith("[Demo] ")
        assert "(fictional)" in o.organisation
        assert o.evidence["_demo"] is True and o.visibility == "public"
        assert o.status in ("open", "closing_soon")
    hosts = {urlsplit(u).hostname for u in db.scalars(sa.select(OpportunitySource.url))}
    hosts |= {urlsplit(u).hostname for u in db.scalars(sa.select(Source.home_url))}
    assert hosts == {"demo.example.com"}

    sources = db.scalars(sa.select(Source)).all()
    assert {s.status for s in sources} == {"active"}
    assert {s.collector_type for s in sources} == {"custom"}
    stats = source_stats(db, [s.id for s in sources])
    assert {stats[s.id].health for s in sources} == {"ok"}

    # Scored for the admin's active (seed) profiles, rules only.
    admin_profiles = db.scalars(sa.select(Profile)).all()
    assert {p.name for p in admin_profiles} == {"Ironji-Trade", "AI lab", "Personal"}
    rows = db.scalars(sa.select(UserOpportunityScore)).all()
    assert len(rows) == 10 * 3
    assert {r.score_breakdown["model"] for r in rows} == {None}
    assert {r.score_breakdown["fit_word"] for r in rows} <= {"possible", None}
    assert r.stats.llm_calls == 0

    # A ranked feed and a digest come out of it.
    admin = r_user(db)
    shown = load_rows(db, admin, opps)
    assert any(row.best and row.best.fit_word == "possible" for row in shown)
    view = build_digest(db, admin, settings, NOW).view
    assert view.items and all(i.title.startswith("[Demo]") for i in view.items)


def r_user(db):
    from blackkite.auth.service import find_user_by_email

    return find_user_by_email(db, ADMIN)


def test_rerun_replaces_the_demo_items(db):
    demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    r = demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    assert r.replaced == 10
    assert count(db, Opportunity) == 10
    assert count(db, Source) == 2
    assert count(db, SourceRun) == 4
    assert count(db, OpportunitySource) == 10


def test_other_users_are_not_scored(db):
    make_user(db, "ben@example.com")
    demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    admin = r_user(db)
    assert {r.user_id for r in db.scalars(sa.select(UserOpportunityScore))} == {
        admin.id
    }


@pytest.fixture
def cli_env(db_url, engine, monkeypatch, tmp_path):
    from blackkite.config import get_settings
    from blackkite.db.session import get_engine, get_sessionmaker

    monkeypatch.chdir(tmp_path)  # no stray .env file
    monkeypatch.setenv("BK_DATABASE_URL", db_url)
    monkeypatch.setenv("BK_FIRST_ADMIN_EMAIL", ADMIN)
    monkeypatch.setenv("BK_MAIL_TRANSPORT", "console")
    monkeypatch.setenv("BK_UNSUBSCRIBE_SECRET", TEST_UNSUBSCRIBE_SECRET)
    for fn in (get_settings, get_engine, get_sessionmaker):
        fn.cache_clear()
    yield monkeypatch
    get_engine().dispose()
    for fn in (get_settings, get_engine, get_sessionmaker):
        fn.cache_clear()


def test_cli_demo_seed_then_dry_run_digest(cli_env, db):
    from blackkite import cli
    from blackkite.config import get_settings

    runner = CliRunner()
    help_text = runner.invoke(cli.app, ["demo-seed", "--help"]).output
    assert "NOT the Phase 4 exit check" in help_text

    cli_env.setenv("BK_ENV", "prod")
    get_settings.cache_clear()
    r = runner.invoke(cli.app, ["demo-seed"])
    assert r.exit_code == 1 and "refused" in r.output
    assert count(db, Opportunity) == 0

    cli_env.setenv("BK_ENV", "dev")
    get_settings.cache_clear()
    r = runner.invoke(cli.app, ["demo-seed"])
    assert r.exit_code == 0, r.output
    assert "10 fictional items on 2 demo sources" in r.output
    assert "not the Phase 4 exit check" in r.output

    r = runner.invoke(cli.app, ["digest", "--user", ADMIN, "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "[Demo]" in r.output


def test_demo_sources_have_a_valid_config_and_run_with_no_items(db):
    """The fictional sources use the allowlisted no-op collector: a forced run
    succeeds, finds nothing and makes no request."""
    from blackkite.collectors.registry import validate_config
    from blackkite.worker import runner
    from tests.fakes import FakeWeb, make_client

    demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    web = FakeWeb()
    for s in db.scalars(sa.select(Source)).all():
        assert s.collector_type == "custom"
        assert validate_config("custom", s.config) == s.config
        run = runner.run_source(db, s, client=make_client(web), now=lambda: NOW)
        assert (run.status, run.items_found, run.error) == ("succeeded", 0, None)
    assert web.requests == []
    assert count(db, Opportunity) == len(DEMO_ITEMS)


def test_fictional_awards_and_plans_for_the_m5_screens(db, app, client, outbox):
    from blackkite.db.models import Award, ProcurementPlanItem
    from blackkite.routes.member import now_utc
    from tests.conftest import sign_in

    r = demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)
    db.commit()
    assert (r.awards, r.plans) == (25, 10)
    awards = db.scalars(sa.select(Award)).all()
    assert Counter(a.category for a in awards) == {
        "transport": 7,
        "ict": 6,
        "construction": 6,
        "office": 6,
    }
    for a in awards:
        assert a.raw == {"_demo": True}
        assert "(fictional)" in a.entity and "(fictional)" in a.winner
        assert a.tender_ref.startswith("DEMO/")
        assert urlsplit(a.url).hostname == "demo.example.com"
    plans = db.scalars(sa.select(ProcurementPlanItem)).all()
    assert len(plans) == 10 and all(p.raw == {"_demo": True} for p in plans)
    assert sum(p.opportunity_id is not None for p in plans) == 1

    app.dependency_overrides[now_utc] = lambda: NOW
    c = sign_in(client, outbox, ADMIN)
    cats = c.get("/api/benchmarks").json()["categories"]
    assert {x["category"] for x in cats if x["median"]} == {
        "transport",
        "ict",
        "construction",
        "office",
    }
    out = c.get("/api/plans").json()["items"]
    assert out and all(i["description"].startswith("[Demo]") for i in out)
    assert "[Demo] Dry freight and last-mile distribution framework" not in {
        i["description"] for i in out
    }
    vaccines = db.scalar(
        sa.select(Opportunity.id).where(Opportunity.title.contains("vaccines"))
    )
    detail = c.get(f"/api/opportunities/{vaccines}").json()["detail"]
    assert detail["benchmark"]["category"] == "transport"

    demo_seed(db, env="dev", admin_email=ADMIN, now=NOW)  # re-run replaces them
    db.commit()
    assert count(db, Award) == 25 and count(db, ProcurementPlanItem) == 10
