"""Decision 49: in either mode, an email with no usable link is skipped and
recorded in the run's warnings (sender, subject, date; never the body); the
run still succeeds when other emails produced items. Offline: fake mailbox."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from blackkite.collectors import email_ingest as ei
from blackkite.db.models import Source, SourceRun
from blackkite.pipeline import ingest
from blackkite.routes.source_schemas import RunOut
from blackkite.worker import runner
from tests.fakes import FakeWeb, make_client
from tests.test_collector_email_ingest import (
    AUTHSERV,
    SENDER,
    FakeMailbox,
    mail,
    source,
)

MESSAGE = {"sender": SENDER, "parse_mode": "message"}
BODY_SECRET = "Body text that must never be stored in a warning"


@pytest.fixture(autouse=True)
def authserv(monkeypatch):
    monkeypatch.setenv("BK_INGEST_AUTHSERV_ID", AUTHSERV)


def inbox() -> FakeMailbox:
    return FakeMailbox(
        {
            "1": mail(
                subject="Tender: cold rooms",
                text="Details: https://board.example/tender/1",
            ),
            "2": mail(
                subject="Weekly round-up (no links)",
                text=BODY_SECRET,
                date="Wed, 25 Nov 2026 07:30:00 +0000",
            ),
            "3": mail(
                subject="Internal link only",
                text=f"{BODY_SECRET} http://192.168.0.10/admin",
            ),
            # Someone else's mail: not this source's, so not a warning.
            "4": mail(sender="news@other.example", text="no link here"),
        }
    )


def test_message_mode_records_each_email_without_a_usable_link():
    box = inbox()
    c = ei.EmailIngestCollector(lambda: box)
    src = source(MESSAGE)
    items = c.fetch(src)
    assert [i.title for i in items] == ["Tender: cold rooms"]
    assert c.warnings == [
        {
            "kind": "email_no_link",
            "message": "Email skipped: no usable link",
            "sender": SENDER,
            "subject": "Weekly round-up (no links)",
            "date": "2026-11-25T07:30:00+00:00",
        },
        {
            "kind": "email_no_link",
            "message": "Email skipped: no usable link",
            "sender": SENDER,
            "subject": "Internal link only",
            "date": "2026-11-24T06:00:00+00:00",
        },
    ]
    assert BODY_SECRET not in json.dumps(c.warnings)
    # Skipped emails are still marked processed, so they are reported once.
    c.after_commit(src)
    assert box.flags["2"] and box.flags["3"] and not box.flags["4"]
    assert c.fetch(src) == [] and c.warnings == []


def test_links_pattern_counts_as_no_usable_link():
    box = FakeMailbox({"1": mail(text="https://social.example/board follow us")})
    c = ei.EmailIngestCollector(lambda: box)
    c.fetch(source({**MESSAGE, "link_pattern": "https://board.example/tender/*"}))
    assert [w["subject"] for w in c.warnings] == ["New tenders this week"]


def test_links_mode_records_emails_with_no_usable_link():
    """Links mode too: an email of this source that yields no item (no safe
    link, or only links with too-short titles) is recorded, headers only; an
    email with items is not, and neither is someone else's mail."""
    box = FakeMailbox(
        {
            "1": mail(
                subject="Tenders",
                html='<a href="https://board.example/tender/9">'
                "Supply of cold rooms to district hospitals</a>",
            ),
            "2": mail(subject="Round-up", text=BODY_SECRET),
            "3": mail(
                subject="Short titles only",
                html=f'<p>{BODY_SECRET}</p><a href="https://board.example/t/1">More</a>',
            ),
            "4": mail(sender="news@other.example", text="no link here"),
        }
    )
    c = ei.EmailIngestCollector(lambda: box)
    items = c.fetch(source({"sender": SENDER}))
    assert [i.url for i in items] == ["https://board.example/tender/9"]
    assert [(w["kind"], w["subject"]) for w in c.warnings] == [
        ("email_no_link", "Round-up"),
        ("email_no_link", "Short titles only"),
    ]
    assert all(w["sender"] == SENDER and w["date"] for w in c.warnings)
    assert BODY_SECRET not in json.dumps(c.warnings)


def test_run_succeeds_and_stores_the_warnings(db, monkeypatch):
    s = Source(
        name="Board alerts",
        home_url="https://board.example",
        streams=["tender"],
        kind="publisher",
        collector_type="email_ingest",
        config=MESSAGE,
        status="testing",
    )
    db.add(s)
    db.commit()
    box = inbox()
    real_build = runner.build_collector

    def build(collector_type, client, **kw):
        return real_build(collector_type, client, mailbox_factory=lambda: box, **kw)

    monkeypatch.setattr(runner, "build_collector", build)
    monkeypatch.setattr(
        ingest,
        "ingest_items",
        lambda session, source, items, **kw: ingest.IngestResult(
            items_found=len(items), items_new=len(items)
        ),
    )
    run = runner.run_source(db, s, client=make_client(FakeWeb()))
    assert (run.status, run.items_found, run.error) == ("succeeded", 1, None)
    assert [w["subject"] for w in run.warnings] == [
        "Weekly round-up (no links)",
        "Internal link only",
    ]
    db.expire_all()
    stored = db.scalars(sa.select(SourceRun).where(SourceRun.source_id == s.id)).one()
    out = RunOut.model_validate(stored).model_dump(mode="json")
    assert out["warnings"][0] == {
        "kind": "email_no_link",
        "message": "Email skipped: no usable link",
        "sender": SENDER,
        "subject": "Weekly round-up (no links)",
        "date": "2026-11-25T07:30:00+00:00",
    }


def test_runs_without_warnings_store_an_empty_list(db):
    s = Source(
        name="Plain",
        home_url="https://plain.example",
        streams=["tender"],
        kind="original",
        collector_type="html_list",
        config={
            "list_url": "https://plain.example/",
            "selectors": {"item": "li", "title": "a"},
        },
    )
    db.add(s)
    db.commit()
    run = SourceRun(source_id=s.id, status="succeeded")
    db.add(run)
    db.commit()
    db.refresh(run)
    assert run.warnings == []
    assert runner.run_warnings(object()) == []
    noisy = type("C", (), {"warnings": [{"kind": "x", "message": "m"}] * 500})()
    assert len(runner.run_warnings(noisy)) == runner.MAX_RUN_WARNINGS
