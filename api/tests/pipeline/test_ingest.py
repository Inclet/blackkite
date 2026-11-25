"""ingest_items against a real Postgres: dedupe, dates, trust states, review flags.

All notices are synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa

from blackkite.db.models import ChangeEvent, Document, Opportunity, OpportunitySource
from blackkite.pipeline.ingest import ingest_items as _ingest
from blackkite.pipeline.ingest import refresh_statuses
from blackkite.pipeline.validate import trust_state
from blackkite.pipeline.visibility import visible_to
from tests.conftest import make_user
from tests.pipeline.conftest import NOW, raw
from tests.pipeline.fakes import FakeFetcher, FakeLLM, q

AGG_TITLE = "SUPPLY OF COLD-CHAIN TRANSPORT SERVICES FOR VACCINES"
ORIG_TITLE = "Supply of cold chain transport services for vaccines"
ORG = "Example Districts Agency"


def ingest(db, source, items, deps, now=NOW):
    return _ingest(db, source, items, deps=deps, now=now)


def opps(db) -> list[Opportunity]:
    return list(db.scalars(sa.select(Opportunity).order_by(Opportunity.created_at)))


def links(db, opp) -> list[OpportunitySource]:
    return list(
        db.scalars(
            sa.select(OpportunitySource).where(
                OpportunitySource.opportunity_id == opp.id
            )
        )
    )


def codes(opp) -> set[str]:
    return {r["code"] for r in opp.evidence.get("_review", [])}


# --- dedupe ---------------------------------------------------------------------------


def test_aggregator_then_original_near_duplicate_becomes_one_record(
    db, make_source, deps
):
    agg = make_source("aggregator")
    orig = make_source("original")
    r1 = ingest(
        db,
        agg,
        [
            raw(
                agg,
                "https://agg.example.com/listing/991?utm_source=feed#top",
                AGG_TITLE,
                organisation=f"{ORG} Ltd",
                listed_deadline="10 Dec 2026",
            )
        ],
        deps(),
    )
    assert (r1.items_found, r1.items_new) == (1, 1)
    [opp] = opps(db)
    assert opp.verification == "aggregator_only"
    assert trust_state(opp.verification, opp.evidence) == "unconfirmed"
    assert opp.evidence["_trust"] == "unconfirmed"

    later = NOW + timedelta(hours=6)
    r2 = ingest(
        db,
        orig,
        [
            raw(
                orig,
                "https://orig.example.org/tenders/T-1",
                ORIG_TITLE,
                organisation=ORG,
                listed_deadline="Closes 10 December 2026 at 5pm",
            )
        ],
        deps(),
        now=later,
    )
    assert (r2.items_found, r2.items_new) == (1, 0)
    [opp] = opps(db)
    ls = {link.url: link for link in links(db, opp)}
    assert set(ls) == {
        "https://agg.example.com/listing/991",
        "https://orig.example.org/tenders/T-1",
    }
    assert ls["https://orig.example.org/tenders/T-1"].is_original is True
    assert ls["https://agg.example.com/listing/991"].is_original is False
    assert ls["https://orig.example.org/tenders/T-1"].first_seen == later
    assert opp.verification == "verified_original"
    # Same day from both: no conflict, the original's time is kept.
    assert opp.evidence["_deadline_conflict"] is False
    assert opp.deadline_at == datetime(2026, 12, 10, 15, tzinfo=UTC)
    assert opp.evidence["deadline_at"]["source_id"] == str(orig.id)
    assert opp.evidence["_trust"] == "confirmed"


def test_same_url_again_only_updates_last_seen(db, make_source, deps):
    src = make_source("publisher")
    item = raw(
        src, "https://jobs.example.org/t/5", "Supply of office furniture for schools"
    )
    ingest(db, src, [item], deps())
    again = raw(
        src,
        "https://JOBS.example.org/t/5/?fbclid=zzz",
        "Supply of office furniture for schools",
    )
    r = ingest(db, src, [again], deps(), now=NOW + timedelta(days=1))
    assert r.items_new == 0
    [opp] = opps(db)
    [link] = links(db, opp)
    assert link.first_seen == NOW
    assert link.last_seen == NOW + timedelta(days=1)


def test_never_merged_across_streams(db, make_source, deps):
    t = make_source("original", streams=("tender",))
    f = make_source("original", streams=("funding",))
    title = "Innovation challenge for cold chain logistics startups"
    ingest(db, t, [raw(t, "https://a.example.org/1", title, organisation=ORG)], deps())
    ingest(db, f, [raw(f, "https://b.example.org/1", title, organisation=ORG)], deps())
    assert sorted(o.stream for o in opps(db)) == ["funding", "tender"]


def test_different_notices_are_kept_apart(db, make_source, deps):
    a = make_source("publisher")
    b = make_source("aggregator")
    ingest(
        db,
        a,
        [
            raw(
                a,
                "https://a.example.org/1",
                ORIG_TITLE,
                organisation=ORG,
                listed_deadline="10 Dec 2026",
            ),
            # Same title, another organisation.
            raw(
                a,
                "https://a.example.org/2",
                ORIG_TITLE,
                organisation="Another Ministry",
                listed_deadline="10 Dec 2026",
            ),
            # Generic title, same organisation, another day.
            raw(
                a,
                "https://a.example.org/3",
                "Invitation for Bids",
                organisation=ORG,
                listed_deadline="12 Dec 2026",
            ),
        ],
        deps(),
    )
    r = ingest(
        db,
        b,
        [
            # Re-advertised two months later: a different notice.
            raw(
                b,
                "https://b.example.com/9",
                AGG_TITLE,
                organisation=ORG,
                listed_deadline="10 Feb 2027",
            ),
            # Generic title on a different day from #3.
            raw(
                b,
                "https://b.example.com/10",
                "Invitation for Bids",
                organisation=ORG,
                listed_deadline="15 Dec 2026",
            ),
            # Generic title on the same day as #3 and same organisation: merged.
            raw(
                b,
                "https://b.example.com/11",
                "INVITATION FOR BIDS",
                organisation=ORG,
                listed_deadline="12 December 2026",
            ),
        ],
        deps(),
    )
    assert r.items_new == 2
    assert len(opps(db)) == 5


# --- trust states and deadline conflicts ---------------------------------------------------


def test_conflicting_deadlines_keep_the_originals_and_flag_review(
    db, make_source, deps
):
    agg = make_source("aggregator")
    orig = make_source("original")
    ingest(
        db,
        agg,
        [
            raw(
                agg,
                "https://agg.example.com/1",
                AGG_TITLE,
                organisation=ORG,
                listed_deadline="8 Dec 2026",
            )
        ],
        deps(),
    )
    ingest(
        db,
        orig,
        [
            raw(
                orig,
                "https://orig.example.org/1",
                ORIG_TITLE,
                organisation=ORG,
                listed_deadline="11 Dec 2026, 10:00",
            )
        ],
        deps(),
    )
    [opp] = opps(db)
    assert opp.deadline_at == datetime(2026, 12, 11, 8, tzinfo=UTC)
    assert opp.evidence["deadline_at"]["rule"] == "original"
    assert opp.needs_review is True
    assert "deadline_conflict" in codes(opp)
    assert opp.evidence["_trust"] == "conflict"
    # The change of deadline is history.
    [ce] = db.scalars(
        sa.select(ChangeEvent).where(ChangeEvent.field == "deadline_at")
    ).all()
    assert ce.old.startswith("2026-12-08") and ce.new.startswith("2026-12-11")


def test_conflict_without_an_original_keeps_the_earliest(db, make_source, deps):
    pub = make_source("publisher")
    news = make_source("news")
    ingest(
        db,
        pub,
        [
            raw(
                pub,
                "https://p.example.org/1",
                ORIG_TITLE,
                organisation=ORG,
                listed_deadline="12 Dec 2026",
            )
        ],
        deps(),
    )
    ingest(
        db,
        news,
        [
            raw(
                news,
                "https://n.example.org/1",
                ORIG_TITLE,
                organisation=ORG,
                listed_deadline="9 Dec 2026",
            )
        ],
        deps(),
    )
    [opp] = opps(db)
    assert opp.deadline_at.astimezone(UTC).date().isoformat() == "2026-12-09"
    assert opp.evidence["deadline_at"]["rule"] == "earliest"
    assert opp.verification == "unverified"
    assert opp.evidence["_trust"] == "conflict"


def test_three_trust_states(db, make_source, deps):
    orig, pub, agg = (
        make_source("original"),
        make_source("publisher"),
        make_source("aggregator"),
    )
    ingest(
        db,
        orig,
        [
            raw(
                orig,
                "https://o.example.org/1",
                "Construction of a district cold store",
                organisation=ORG,
            )
        ],
        deps(),
    )
    ingest(
        db,
        pub,
        [
            raw(
                pub,
                "https://p.example.org/2",
                "Annual supply of laboratory reagents",
                organisation=ORG,
            )
        ],
        deps(),
    )
    ingest(
        db,
        agg,
        [
            raw(
                agg,
                "https://a.example.org/3",
                "Consultancy for a feasibility study on rail",
                organisation=ORG,
            )
        ],
        deps(),
    )
    by_title = {o.title: o for o in opps(db)}
    assert (
        by_title["Construction of a district cold store"].evidence["_trust"]
        == "confirmed"
    )
    assert (
        by_title["Construction of a district cold store"].verification
        == "verified_original"
    )
    assert (
        by_title["Annual supply of laboratory reagents"].evidence["_trust"]
        == "unconfirmed"
    )
    assert by_title["Annual supply of laboratory reagents"].verification == "unverified"
    assert (
        by_title["Consultancy for a feasibility study on rail"].evidence["_trust"]
        == "unconfirmed"
    )
    assert (
        by_title["Consultancy for a feasibility study on rail"].verification
        == "aggregator_only"
    )


# --- dates --------------------------------------------------------------------------------


def test_deadline_without_a_year_is_null_and_flagged(db, make_source, deps):
    src = make_source("publisher", streams=("event",))
    ingest(
        db,
        src,
        [
            raw(
                src,
                "https://e.example.org/1",
                "Kigali logistics breakfast",
                listed_deadline="25 November",
            )
        ],
        deps(),
    )
    [opp] = opps(db)
    assert opp.deadline_at is None
    assert opp.needs_review is True
    assert "date" in codes(opp)
    assert opp.evidence["deadline_at"]["raw"] == "25 November"
    assert opp.evidence["deadline_at"]["status"] == "no_year"
    assert opp.status == "open"


def test_out_of_window_published_date_is_dropped(db, make_source, deps):
    src = make_source("publisher")
    ingest(
        db,
        src,
        [
            raw(
                src,
                "https://p.example.org/old",
                "Supply of maize seed to cooperatives",
                listed_published="3 March 2023",
            )
        ],
        deps(),
    )
    [opp] = opps(db)
    assert opp.published_at is None
    assert opp.evidence["published_at"]["status"] == "out_of_window"
    assert opp.needs_review is True


def test_passed_deadline_is_expired_and_close_one_is_closing_soon(
    db, make_source, deps
):
    src = make_source("original")
    ingest(
        db,
        src,
        [
            raw(
                src,
                "https://o.example.org/a",
                "Rehabilitation of feeder roads",
                listed_deadline="24 Nov 2026 10:00",
            ),
            raw(
                src,
                "https://o.example.org/b",
                "Provision of security services",
                listed_deadline="1 Dec 2026",
            ),
            raw(
                src,
                "https://o.example.org/c",
                "Supply of solar water pumps",
                listed_deadline="31 Dec 2026",
            ),
        ],
        deps(),
    )
    status = {o.title: o.status for o in opps(db)}
    assert status == {
        "Rehabilitation of feeder roads": "expired",
        "Provision of security services": "closing_soon",
        "Supply of solar water pumps": "open",
    }
    # Time passing moves them on, with history.
    assert refresh_statuses(db, NOW + timedelta(days=8)) == 1
    assert {o.title: o.status for o in opps(db)}[
        "Provision of security services"
    ] == "expired"


# --- extraction ---------------------------------------------------------------------------

DETAIL = b"""<html><body><h1>Supply of refrigerated transport services for vaccines</h1>
<p>Example Districts Agency (EDA) invites sealed bids.</p>
<p>Estimated budget: FRW 25,000,000.</p>
<p>Bids close on 14 December 2026 at 10:00 am.</p>
<p>Published 20 November 2026.</p>
<p>The event launch is on 25 November.</p>
<a href="/docs/tender.pdf">Bidding document</a></body></html>"""


def detail_reply(**over):
    reply = {
        "stream": q("tender", "invites sealed bids"),
        "title": q("Supply of refrigerated transport services for vaccines"),
        "organisation": q(ORG, "Example Districts Agency (EDA)"),
        "organisation_short": q("EDA", "(EDA)"),
        "summary": q(
            "EDA wants a carrier for chilled vaccines. Bids close mid-December.",
            "invites sealed bids",
        ),
        "deadline_at": q(
            "2026-12-14T10:00", "Bids close on 14 December 2026 at 10:00 am."
        ),
        "published_at": q("2026-11-20", "Published 20 November 2026."),
        "value_amount": {
            "value": "25,000,000",
            "snippet": "Estimated budget: FRW 25,000,000.",
        },
        "value_currency": q("FRW", "FRW 25,000,000"),
        "tags": [
            {
                "tag": "cold chain transport",
                "kind": "service_type",
                "snippet": "refrigerated transport",
            }
        ],
    }
    reply.update(over)
    return reply


def test_extraction_fills_fields_documents_embedding_and_evidence(
    db, make_source, deps, embedder
):
    from tests.pipeline.pdfgen import make_pdf

    src = make_source("original")
    fetcher = FakeFetcher(
        {
            "https://o.example.org/t/7": ("text/html", DETAIL),
            "https://o.example.org/docs/tender.pdf": (
                "application/pdf",
                make_pdf("Lot 1: 20 refrigerated trucks"),
            ),
        }
    )
    llm = FakeLLM(detail_reply())
    r = ingest(
        db,
        src,
        [raw(src, "https://o.example.org/t/7", "Invitation for Bids")],
        deps(llm=llm, embedder=embedder, fetcher=fetcher),
    )
    assert r.items_new == 1
    [opp] = opps(db)
    assert opp.title == "Supply of refrigerated transport services for vaccines"
    assert opp.organisation_short == "EDA"
    assert opp.value_amount == Decimal("25000000.00") and opp.value_currency == "RWF"
    assert opp.deadline_at == datetime(2026, 12, 14, 8, tzinfo=UTC)
    assert opp.published_at == datetime(2026, 11, 19, 22, tzinfo=UTC)
    assert opp.tags == ["service:cold chain transport"]
    assert opp.embedding is not None and len(opp.embedding) == embedder.dim
    assert opp.needs_review is False, opp.evidence.get("_review")
    ev = opp.evidence
    assert ev["_extraction"]["model"] == "fake-extract-1"
    assert ev["_extraction"]["prompt_version"] == "extract-v1"
    assert ev["_embedding"]["model"] == "fake-embed-1"
    assert ev["deadline_at"]["snippet"] == "Bids close on 14 December 2026 at 10:00 am."
    assert ev["value_amount"]["snippet"] == "Estimated budget: FRW 25,000,000."
    # The PDF text reached the model.
    assert "20 refrigerated trucks" in llm.calls[0]["user"]
    docs = db.scalars(
        sa.select(Document).where(Document.opportunity_id == opp.id)
    ).all()
    assert sorted(d.url for d in docs) == [
        "https://o.example.org/docs/tender.pdf",
        "https://o.example.org/t/7",
    ]
    assert all(d.file_path and d.extracted_text for d in docs)
    assert "Supply of refrigerated" in embedder.texts[0]


def test_extracted_date_without_year_and_invented_snippets_are_not_kept(
    db, make_source, deps, embedder
):
    src = make_source("original", streams=("event",))
    fetcher = FakeFetcher({"https://o.example.org/ev/1": ("text/html", DETAIL)})
    reply = detail_reply(
        stream=q("event", "The event launch"),
        event_start=q("2026-11-25", "The event launch is on 25 November."),
        deadline_at=q(
            "2026-12-20", "Applications close 20 December 2026"
        ),  # not in text
        value_amount={"value": 9, "snippet": "budget of nine"},
    )
    ingest(
        db,
        src,
        [raw(src, "https://o.example.org/ev/1", "Launch")],
        deps(llm=FakeLLM(reply), embedder=embedder, fetcher=fetcher),
    )
    [opp] = opps(db)
    assert opp.event_start is None
    assert opp.evidence["event_start"]["status"] == "no_year"
    assert opp.evidence["event_start"]["raw"] == "The event launch is on 25 November."
    assert opp.deadline_at is None
    assert opp.value_amount is None
    assert opp.needs_review is True
    assert {"date", "extraction_check"} <= codes(opp)


def test_non_opportunity_is_not_stored(db, make_source, deps):
    src = make_source("news", streams=("funding", "investment", "event"))
    llm = FakeLLM({"is_opportunity": False, "not_opportunity_reason": "news story"})
    r = ingest(
        db,
        src,
        [raw(src, "https://n.example.org/story", "Minister opens new road")],
        deps(llm=llm),
    )
    assert (r.items_found, r.items_new, r.items_failed) == (1, 0, 0)
    assert opps(db) == []


def test_multi_stream_source_uses_extracted_stream(db, make_source, deps, embedder):
    src = make_source("news", streams=("funding", "investment", "event"))
    text = "Example Fund opens a grant call for agritech startups"
    llm = FakeLLM({"stream": q("funding", "grant call"), "title": q(text)})
    ingest(
        db,
        src,
        [raw(src, "https://n.example.org/grant", text)],
        deps(llm=llm, embedder=embedder),
    )
    [opp] = opps(db)
    assert opp.stream == "funding"
    assert "stream_unknown" not in codes(opp)


# --- missing keys ------------------------------------------------------------------------


def test_missing_keys_keep_the_item_and_flag_review_then_recover(
    db, make_source, deps, embedder
):
    src = make_source("original")
    item = raw(
        src,
        "https://o.example.org/t/7",
        "Invitation for Bids",
        organisation=ORG,
        listed_deadline="14 Dec 2026",
    )
    r = ingest(db, src, [item], deps())
    assert (r.items_new, r.items_failed) == (1, 0)
    [opp] = opps(db)
    assert opp.title == "Invitation for Bids" and opp.organisation == ORG
    assert opp.needs_review is True
    details = " | ".join(x["detail"] for x in opp.evidence["_review"])
    assert "ANTHROPIC_API_KEY" in details and "VOYAGE_API_KEY" in details
    assert opp.embedding is None and "_extraction" not in opp.evidence

    # Keys set later: the next sighting extracts and embeds, and the flag clears.
    fetcher = FakeFetcher({"https://o.example.org/t/7": ("text/html", DETAIL)})
    r = ingest(
        db,
        src,
        [item],
        deps(llm=FakeLLM(detail_reply()), embedder=embedder, fetcher=fetcher),
    )
    assert r.items_new == 0
    db.refresh(opp)
    assert opp.title == "Supply of refrigerated transport services for vaccines"
    assert opp.embedding is not None
    assert opp.evidence["_review"] == []
    assert opp.needs_review is False


def test_llm_failure_keeps_item_with_reason(db, make_source, deps, embedder):
    from blackkite.llm.client import LLMError

    src = make_source("original")
    ingest(
        db,
        src,
        [raw(src, "https://o.example.org/x", "Supply of diesel generators")],
        deps(llm=FakeLLM(error=LLMError("overloaded")), embedder=embedder),
    )
    [opp] = opps(db)
    assert opp.needs_review is True
    assert "extraction_failed" in codes(opp)


# --- batch isolation ------------------------------------------------------------------------


def test_one_bad_item_does_not_sink_the_batch(db, make_source, deps):
    src = make_source("publisher")
    other = make_source("publisher")
    items = [
        raw(src, "https://p.example.org/1", "Supply of school uniforms"),
        raw(other, "https://p.example.org/2", "Wrong source id"),  # rejected
        raw(src, "https://p.example.org/3", "   "),  # no title
        raw(src, "https://p.example.org/4", "Supply of hospital beds"),
    ]

    def boom(user):
        if "hospital beds" in user:
            raise RuntimeError("unexpected")
        return {"stream": q("tender", "Supply of school uniforms")}

    r = ingest(db, src, items, deps(llm=FakeLLM(boom)))
    assert (r.items_found, r.items_new, r.items_failed) == (4, 1, 3)
    assert [o.title for o in opps(db)] == ["Supply of school uniforms"]


# --- visibility -------------------------------------------------------------------------------


def test_testing_source_items_are_hidden_from_members_until_promoted(
    db, make_source, deps
):
    member = make_user(db, "member@example.org")
    admin = make_user(db, "admin@example.org", role="admin")
    testing = make_source("publisher", status="testing")
    ingest(
        db,
        testing,
        [raw(testing, "https://t.example.org/1", "Supply of laboratory fridges")],
        deps(),
    )
    private = Opportunity(
        stream="tender",
        title="My land lead",
        visibility="private",
        owner_user_id=member.id,
    )
    db.add(private)
    db.flush()

    def titles(user, is_admin):
        q_ = sa.select(Opportunity.title).where(visible_to(user.id, is_admin=is_admin))
        return set(db.scalars(q_))

    assert titles(member, False) == {"My land lead"}
    assert titles(admin, True) == {
        "Supply of laboratory fridges"
    }  # not others' private items
    testing.status = "active"
    db.flush()
    assert titles(member, False) == {"My land lead", "Supply of laboratory fridges"}
    testing.status = "paused"
    db.flush()
    assert "Supply of laboratory fridges" in titles(member, False)
    testing.status = "retired"
    db.flush()
    assert titles(member, False) == {"My land lead"}


def test_collected_items_never_merge_into_private_items(db, make_source, deps):
    member = make_user(db, "m2@example.org")
    db.add(
        Opportunity(
            stream="tender",
            title=ORIG_TITLE,
            organisation=ORG,
            visibility="private",
            owner_user_id=member.id,
        )
    )
    db.flush()
    src = make_source("original")
    r = ingest(
        db,
        src,
        [raw(src, "https://o.example.org/p", ORIG_TITLE, organisation=ORG)],
        deps(),
    )
    assert r.items_new == 1
    assert len(opps(db)) == 2


# --- deadline changes between runs ------------------------------------------------------


def _listed(src, url, deadline, title=ORIG_TITLE):
    return raw(src, url, title, organisation=ORG, listed_deadline=deadline)


def _source_deadline_events(db, opp) -> list[ChangeEvent]:
    return list(
        db.scalars(
            sa.select(ChangeEvent).where(
                ChangeEvent.opportunity_id == opp.id,
                ChangeEvent.field == "source_deadline",
            )
        )
    )


def _extract_reply(deadline_iso, snippet):
    return {
        "title": q(ORIG_TITLE),
        "organisation": q(ORG),
        "deadline_at": q(deadline_iso, snippet),
    }


def test_extension_on_the_original_source_moves_the_deadline(
    db, make_source, deps, embedder
):
    orig = make_source("original", name="Example e-procurement")
    url = "https://orig.example.org/t/1"
    text = "Bids close on 14 December 2026."
    fetcher = FakeFetcher({url: ("text/html", f"<p>{text}</p>".encode())})
    ingest(
        db,
        orig,
        [_listed(orig, url, "14 Dec 2026")],
        deps(
            llm=FakeLLM(_extract_reply("2026-12-14", text)),
            embedder=embedder,
            fetcher=fetcher,
        ),
    )
    [opp] = opps(db)
    assert opp.deadline_at.date().isoformat() == "2026-12-14"
    assert "deadline_extracted" in opp.evidence["_sources"][str(orig.id)]
    assert opp.needs_review is False, opp.evidence["_review"]

    llm = FakeLLM(_extract_reply("2026-12-14", text))
    later = NOW + timedelta(days=1)
    ingest(
        db,
        orig,
        [_listed(orig, url, "21 Dec 2026")],
        deps(llm=llm, embedder=embedder, fetcher=fetcher),
        now=later,
    )
    db.refresh(opp)
    assert opp.deadline_at.date().isoformat() == "2026-12-21"
    assert opp.evidence["deadline_at"]["source_id"] == str(orig.id)
    assert opp.needs_review is True
    [reason] = [r for r in opp.evidence["_review"] if r["code"] == "deadline_changed"]
    assert "deadline changed at Example e-procurement" in reason["detail"]
    assert "2026-12-14 -> 2026-12-21" in reason["detail"]
    entry = opp.evidence["_sources"][str(orig.id)]
    assert "deadline_extracted" not in entry
    assert [h["kind"] for h in entry["deadline_history"]] == ["listed", "extracted"]
    [ce] = db.scalars(
        sa.select(ChangeEvent).where(ChangeEvent.field == "deadline_at")
    ).all()
    assert ce.old.startswith("2026-12-14") and ce.new.startswith("2026-12-21")
    [sce] = _source_deadline_events(db, opp)
    assert sce.old["source_id"] == str(orig.id)
    assert sce.old["value"].startswith("2026-12-14")
    assert sce.new["value"].startswith("2026-12-21")

    # Same listing again: no further change, the newer value stays.
    ingest(db, orig, [_listed(orig, url, "21 Dec 2026")], deps(), now=later)
    db.refresh(opp)
    assert opp.deadline_at.date().isoformat() == "2026-12-21"
    assert len(_source_deadline_events(db, opp)) == 1


def test_extension_on_an_aggregator_only_keeps_the_original_and_flags(
    db, make_source, deps
):
    orig = make_source("original")
    agg = make_source("aggregator", name="Example aggregator")
    ingest(db, orig, [_listed(orig, "https://o.example.org/1", "14 Dec 2026")], deps())
    ingest(
        db,
        agg,
        [_listed(agg, "https://a.example.com/1", "14 Dec 2026", AGG_TITLE)],
        deps(),
    )
    [opp] = opps(db)
    assert opp.evidence["_deadline_conflict"] is False

    ingest(
        db,
        agg,
        [_listed(agg, "https://a.example.com/1", "21 Dec 2026", AGG_TITLE)],
        deps(),
        now=NOW + timedelta(days=1),
    )
    db.refresh(opp)
    assert opp.deadline_at.date().isoformat() == "2026-12-14"
    assert opp.evidence["deadline_at"]["rule"] == "original"
    assert opp.evidence["_deadline_conflict"] is True
    assert opp.evidence["_trust"] == "conflict"
    assert {"deadline_changed", "deadline_conflict"} <= codes(opp)
    assert opp.needs_review is True
    [sce] = _source_deadline_events(db, opp)
    assert sce.new["source_id"] == str(agg.id)
    # The catalogue deadline did not move.
    assert not db.scalars(
        sa.select(ChangeEvent).where(ChangeEvent.field == "deadline_at")
    ).all()


def test_shortened_deadline_is_taken_and_flagged(db, make_source, deps):
    pub = make_source("publisher")
    url = "https://p.example.org/1"
    ingest(db, pub, [_listed(pub, url, "21 Dec 2026")], deps())
    ingest(db, pub, [_listed(pub, url, "10 Dec 2026")], deps(), now=NOW + timedelta(1))
    [opp] = opps(db)
    assert opp.deadline_at.date().isoformat() == "2026-12-10"
    assert "deadline_changed" in codes(opp)
    assert len(_source_deadline_events(db, opp)) == 1


def test_listed_deadline_without_a_year_does_not_override_extracted(
    db, make_source, deps, embedder
):
    orig = make_source("original")
    url = "https://o.example.org/t/9"
    text = "Bids close on 14 December 2026."
    fetcher = FakeFetcher({url: ("text/html", f"<p>{text}</p>".encode())})
    ingest(
        db,
        orig,
        [_listed(orig, url, "14 Dec")],
        deps(
            llm=FakeLLM(_extract_reply("2026-12-14", text)),
            embedder=embedder,
            fetcher=fetcher,
        ),
    )
    ingest(db, orig, [_listed(orig, url, "21 Dec")], deps(), now=NOW + timedelta(1))
    [opp] = opps(db)
    assert opp.deadline_at.date().isoformat() == "2026-12-14"
    assert "deadline_changed" not in codes(opp)
    assert _source_deadline_events(db, opp) == []

    # A dated listing followed by an undated one keeps the dated value as well.
    pub = make_source("publisher")
    purl = "https://p.example.org/2"
    title = "Supply of diesel generators to district offices"
    ingest(db, pub, [_listed(pub, purl, "12 Dec 2026", title)], deps())
    ingest(
        db, pub, [_listed(pub, purl, "19 Dec", title)], deps(), now=NOW + timedelta(1)
    )
    [gen] = [o for o in opps(db) if o.title == title]
    assert gen.deadline_at.date().isoformat() == "2026-12-12"
    assert "deadline_changed" not in codes(gen)


def test_extension_moves_status_back_to_open(db, make_source, deps):
    pub = make_source("publisher")
    ingest(
        db,
        pub,
        [
            _listed(pub, "https://p.example.org/x", "20 Nov 2026"),
            _listed(
                pub,
                "https://p.example.org/y",
                "28 Nov 2026",
                "Supply of laboratory reagents to referral hospitals",
            ),
        ],
        deps(),
    )
    by_url = {}
    for o in opps(db):
        [link] = links(db, o)
        by_url[link.url] = o
    expired, soon = by_url["https://p.example.org/x"], by_url["https://p.example.org/y"]
    assert (expired.status, soon.status) == ("expired", "closing_soon")

    ingest(
        db,
        pub,
        [
            _listed(pub, "https://p.example.org/x", "10 Jan 2027"),
            _listed(
                pub,
                "https://p.example.org/y",
                "21 Dec 2026",
                "Supply of laboratory reagents to referral hospitals",
            ),
        ],
        deps(),
        now=NOW + timedelta(hours=1),
    )
    for opp, old in ((expired, "expired"), (soon, "closing_soon")):
        db.refresh(opp)
        assert opp.status == "open"
        [ce] = db.scalars(
            sa.select(ChangeEvent).where(
                ChangeEvent.opportunity_id == opp.id, ChangeEvent.field == "status"
            )
        ).all()
        assert (ce.old, ce.new) == (old, "open")
        assert "deadline_changed" in codes(opp)


def test_multi_stream_source_investment_item_has_no_advice(
    db, make_source, deps, embedder
):
    src = make_source("news", streams=("funding", "investment", "event"))
    text = "Treasury bond issue: a 5-year bond, coupon 12.5%, auction 9 December 2026."
    advice = "A five-year bond at 12.5%. Investors should buy before the auction."
    for stream in (None, "investment"):
        reply = {"title": q(text), "summary": q(advice, "a 5-year bond")}
        if stream:
            reply["stream"] = q(stream, "Treasury bond issue")
        url = f"https://n.example.org/bond-{stream}"
        ingest(
            db,
            src,
            [raw(src, url, text)],
            deps(llm=FakeLLM(reply), embedder=embedder),
        )
    found = opps(db)
    assert len(found) == 2
    for opp in found:
        assert opp.summary is None
        assert "extraction_check" in codes(opp)
