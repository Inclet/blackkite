"""Every collector type through the runner (source_run rows), the test run (writes
nothing) and the promotion gate. Fakes only: FakeWeb, a fake renderer, a fake
mailbox. Ingest is replaced by a recorder; the pipeline has its own tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import httpx
import pytest
import sqlalchemy as sa
from pydantic import SecretStr

from blackkite.collectors import browser_list, email_ingest
from blackkite.db.models import (
    COLLECTOR_TYPES,
    HttpCache,
    Opportunity,
    Source,
    SourceRun,
)
from blackkite.pipeline import ingest
from blackkite.sources import service
from blackkite.sources.testrun import preview_source
from blackkite.worker import runner
from tests.fakes import FakeWeb, make_client

NOW = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)
H = "site.example"
SENDER = "alerts@site.example"
LIST_HTML = (
    '<ul><li><a href="/n/1">Supply of school desks</a></li>'
    '<li><a href="/n/2">Supply of hospital beds</a></li></ul>'
)
RSS = f"""<rss version="2.0"><channel><title>T</title>
<item><title>Grant call for agri-food startups</title><link>https://{H}/f/1</link></item>
<item><title>Accelerator intake 2027</title><link>https://{H}/f/2</link></item>
</channel></rss>"""
JSONLD = f"""<script type="application/ld+json">
[{{"@type": "Event", "name": "Kigali logistics summit", "url": "https://{H}/e/1",
   "startDate": "2027-02-01"}},
 {{"@type": "Event", "name": "AI meetup Kigali", "url": "https://{H}/e/2",
   "startDate": "2027-02-03"}}]</script>"""

CONFIGS = {
    "html_list": {
        "list_url": f"https://{H}/list",
        "selectors": {"item": "li", "title": "a"},
    },
    "browser_list": {
        "list_url": f"https://{H}/app",
        "wait_for": "li",
        "selectors": {"item": "li", "title": "a"},
    },
    "rss": {"feed_url": f"https://{H}/feed"},
    "json_api": {
        "endpoint": f"https://{H}/api",
        "mapping": {"list": "items", "title": "t", "url": "u"},
    },
    "search_query": {"queries": ["tender desks"], "domains": [H]},
    "email_ingest": {"sender": SENDER},
    "custom": {
        "collector": "jsonld_events",
        "options": {"list_url": f"https://{H}/ev"},
    },
}


def test_every_type_has_a_case():
    assert set(CONFIGS) == set(COLLECTOR_TYPES)


class FakeRenderer:
    def render(self, url, *, wait_for=None):
        return browser_list.RenderedPage(url=url, html=LIST_HTML)

    def close(self):
        pass


def email_bytes() -> bytes:
    m = EmailMessage()
    m["From"] = SENDER
    m["Subject"] = "New tenders"
    m["Date"] = "Tue, 24 Nov 2026 06:00:00 +0000"
    m["Authentication-Results"] = "mx; dkim=pass header.d=site.example"
    m.set_content(
        "Supply of school desks to districts https://site.example/n/1\n"
        "Supply of hospital beds nationwide https://site.example/n/2\n"
    )
    return bytes(m)


class FakeMailbox:
    def __init__(self):
        self.flags: dict[str, set[str]] = {"1": set()}
        self.readonly: list[bool] = []

    def select(self, folder, *, readonly):
        self.readonly.append(readonly)

    def supports_keywords(self):
        return True

    def search(self, criteria):
        kw = criteria[criteria.index("UNKEYWORD") + 1]
        return [u for u, f in self.flags.items() if kw not in f]

    def size(self, uid):
        return 1000

    def fetch(self, uid):
        return email_bytes()

    def add_flag(self, uids, flag):
        for u in uids:
            self.flags[u].add(flag)

    def logout(self):
        pass


@pytest.fixture
def world(monkeypatch):
    web = FakeWeb()
    web.html(H, "/list", LIST_HTML)
    web.add(H, "/feed", httpx.Response(200, text=RSS))
    web.add(
        H,
        "/api",
        httpx.Response(
            200,
            content=json.dumps(
                {"items": [{"t": "Notice A", "u": "/a"}, {"t": "Notice B", "u": "/b"}]}
            ).encode(),
            headers={"content-type": "application/json"},
        ),
    )
    web.html(H, "/ev", JSONLD)
    web.add(
        "api.search.brave.com",
        "/res/v1/web/search",
        httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"title": "Supply of desks", "url": f"https://{H}/n/1"},
                        {"title": "Supply of beds", "url": f"https://{H}/n/2"},
                    ]
                }
            },
        ),
    )
    box = FakeMailbox()
    monkeypatch.setattr(browser_list, "default_renderer", lambda client: FakeRenderer())
    monkeypatch.setattr(email_ingest, "mailbox_from_env", lambda: box)
    return web, box


@pytest.fixture
def recorded(monkeypatch):
    calls = []

    def fake_ingest(session, source, items, **kw):
        calls.append((source.collector_type, [i.url for i in items]))
        for i in items:
            session.add(Opportunity(stream=source.streams[0], title=i.title))
        session.flush()
        return ingest.IngestResult(items_found=len(items), items_new=len(items))

    monkeypatch.setattr(ingest, "ingest_items", fake_ingest)
    return calls


def add(db, ctype) -> Source:
    s = Source(
        name=f"{ctype} source",
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original" if ctype != "search_query" else "aggregator",
        collector_type=ctype,
        config=CONFIGS[ctype],
        status="testing",
        rate_limit=1.0,
        created_at=NOW - timedelta(days=2),
    )
    db.add(s)
    db.commit()
    return s


def counts(db):
    db.expire_all()
    return {
        m.__name__: db.scalar(sa.select(sa.func.count()).select_from(m))
        for m in (Source, SourceRun, Opportunity, HttpCache)
    }


@pytest.mark.parametrize("ctype", sorted(CONFIGS))
def test_runner_test_run_and_promotion_gate(ctype, db, world, recorded):
    web, box = world
    key = SecretStr("k-test")
    s = add(db, ctype)

    # Test run: items shown, nothing written (no rows, no cache, no mail flags).
    before = counts(db)
    preview = preview_source(s, make_client(web), brave_api_key=key)
    assert preview.ok, preview.error
    assert preview.total_parsed == 2 and len(preview.items) == 2
    assert counts(db) == before
    assert box.flags["1"] == set()

    # Not promotable before two good runs.
    with pytest.raises(service.PromotionBlocked):
        service.change_status(db, s, "active")
    db.rollback()

    first = runner.run_source(
        db, s, client=make_client(web), brave_api_key=key, now=lambda: NOW
    )
    assert (first.status, first.items_found, first.error) == ("succeeded", 2, None)
    if ctype == "email_ingest":
        # Processed mail is flagged, so the second run reads it again only after
        # we clear the flag (a newsletter arriving the next week).
        box.flags["1"].clear()
    second = runner.run_source(
        db,
        s,
        client=make_client(web),
        brave_api_key=key,
        now=lambda: NOW + timedelta(hours=1),
    )
    assert (second.status, second.items_found) == ("succeeded", 2)
    service.change_status(db, s, "active")
    db.commit()
    assert s.status == "active"
    assert [c[0] for c in recorded] == [ctype, ctype]


def test_email_run_without_a_configured_inbox_fails_cleanly(db, recorded, monkeypatch):
    monkeypatch.setattr(
        email_ingest,
        "mailbox_from_env",
        lambda: email_ingest.ImapMailbox(email_ingest.ImapSettings(_env_file=None)),
    )
    for k in ("HOST", "USER", "PASSWORD"):
        monkeypatch.delenv(f"BK_INGEST_IMAP_{k}", raising=False)
    s = add(db, "email_ingest")
    run = runner.run_source(db, s, client=make_client(FakeWeb()), now=lambda: NOW)
    assert run.status == "failed" and "no ingest mailbox configured" in run.error
    assert recorded == []


@pytest.mark.parametrize("ctype", sorted(CONFIGS))
def test_bad_config_fails_the_run_with_a_readable_error(ctype, db, recorded):
    s = add(db, ctype)
    s.config = {"nonsense": True}
    db.commit()
    run = runner.run_source(db, s, client=make_client(FakeWeb()), now=lambda: NOW)
    assert run.status == "failed"
    assert f"invalid {ctype} config" in run.error
    assert "not implemented" not in run.error


def test_email_flags_are_set_only_after_the_ingest_commits(db, world, monkeypatch):
    web, box = world
    s = add(db, "email_ingest")
    seen_at_ingest = []

    def check_then_ingest(session, source, items, **kw):
        # The ingest runs before the commit: nothing may be flagged yet.
        seen_at_ingest.append(set(box.flags["1"]))
        return ingest.IngestResult(items_found=len(items), items_new=len(items))

    monkeypatch.setattr(ingest, "ingest_items", check_then_ingest)
    run = runner.run_source(db, s, client=make_client(web), now=lambda: NOW)
    assert run.status == "succeeded"
    assert seen_at_ingest == [set()]
    assert box.flags["1"] == {email_ingest.done_keyword(s.id)}


def test_email_ingest_rollback_leaves_mail_unflagged(db, world, monkeypatch):
    web, box = world
    s = add(db, "email_ingest")

    def failing_ingest(session, source, items, **kw):
        session.add(Opportunity(stream="tender", title="half-written"))
        session.flush()
        raise RuntimeError("extract failed")

    monkeypatch.setattr(ingest, "ingest_items", failing_ingest)
    run = runner.run_source(db, s, client=make_client(web), now=lambda: NOW)
    assert run.status == "failed" and "extract failed" in run.error
    assert box.flags["1"] == set()
    assert counts(db)["Opportunity"] == 0
    # The next run reads the same mail again.
    calls = []
    monkeypatch.setattr(
        ingest,
        "ingest_items",
        lambda session, source, items, **kw: (
            calls.append(len(items))
            or ingest.IngestResult(items_found=len(items), items_new=len(items))
        ),
    )
    again = runner.run_source(
        db, s, client=make_client(web), now=lambda: NOW + timedelta(hours=1)
    )
    assert again.status == "succeeded" and calls == [2]
    assert box.flags["1"] == {email_ingest.done_keyword(s.id)}


def test_a_failing_after_commit_keeps_the_run_succeeded(db, world, recorded):
    web, box = world
    s = add(db, "email_ingest")

    def broken(uids, flag):
        raise OSError("connection reset")

    box.add_flag = broken
    run = runner.run_source(db, s, client=make_client(web), now=lambda: NOW)
    assert (run.status, run.items_found, run.error) == ("succeeded", 2, None)
    assert box.flags["1"] == set()
