"""End to end: a source run through collect -> normalise -> dedupe -> enrich ->
extract -> validate -> catalogue, offline (spec 5 stages 1-6).

The web is a MockTransport behind the real guarded client (robots.txt, per-host
delay, User-Agent, size cap); the model and the embedder are fakes. Every notice,
page and PDF here is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from pydantic import SecretStr

from blackkite.db.models import Document, Opportunity, OpportunitySource, Source
from blackkite.pipeline.dates import kigali_date
from blackkite.pipeline.validate import trust_state
from blackkite.worker import runner
from tests.fakes import FakeWeb, make_client, pipeline_deps
from tests.pipeline.fakes import FakeEmbedder, FakeLLM, q
from tests.pipeline.pdfgen import make_pdf

NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
ORIG = "procure.example"  # the issuer's own portal
JOBS = "jobs.example"  # a publisher site reached only through search
BRAVE = "api.search.brave.com"

VACCINES = "Transport of vaccines in refrigerated trucks"
PUMPS = "Supply of solar water pumps"
ORG = "Example District Health Office"

LIST_HTML = f"""<html><body><ul class="notices">
<li><a href="/notice/101?utm_source=list">Invitation for Bids</a>
    <span class="org">{ORG}</span><span class="dl">12 Dec 2026</span></li>
<li><a href="/notice/102">Supply of hospital linen</a>
    <span class="org">Example Referral Hospital</span><span class="dl">19 Dec 2026</span></li>
</ul></body></html>"""

DETAIL_101 = f"""<html><head><script>track()</script></head><body>
<h1>Invitation for Bids</h1>
<p>{ORG} invites sealed bids for the {VACCINES.lower()} to district health centres.</p>
<p><a href="/docs/101.pdf">Bidding document (PDF)</a></p>
</body></html>"""

PDF_101 = (
    "Bidding document. Bids close 12 December 2026. Bidders must hold "
    "at least 10 refrigerated trucks. Bid security RWF 500,000."
)

DETAIL_102 = """<html><body><h1>Supply of hospital linen</h1>
<p>Example Referral Hospital seeks a supplier of bed linen and gowns.
Deadline for submission: 19 December 2026.</p></body></html>"""

DETAIL_PUMPS = f"""<html><body><h1>{PUMPS}</h1>
<p>A cooperative union is buying solar water pumps for irrigation schemes.
Estimated budget: RWF 45,000,000. Submissions close 15 December 2026.</p>
</body></html>"""


def reply(text: str) -> dict:
    """Fake extraction: every value quotes text that is really in the input."""
    if "refrigerated trucks" in text:
        return {
            "stream": q("tender", "invites sealed bids"),
            "subtype": q("tender", "Invitation for Bids"),
            "title": q(VACCINES, VACCINES.lower()),
            "organisation": q(ORG),
            "summary": q("A district office wants vaccines moved in cold trucks."),
            "deadline_at": q("2026-12-12", "Bids close 12 December 2026"),
            "fees": q("Bid security RWF 500,000"),
            "requirements": [
                {
                    "text": "At least 10 refrigerated trucks",
                    "snippet": "at least 10 refrigerated trucks",
                }
            ],
            "tags": [
                {"tag": "cold chain", "kind": "service_type", "snippet": "refrigerated"}
            ],
        }
    if "hospital linen" in text:
        return {
            "stream": q("tender", "Supply of hospital linen"),
            "title": q("Supply of hospital linen"),
            "organisation": q("Example Referral Hospital"),
            "deadline_at": q("2026-12-19", "Deadline for submission: 19 December 2026"),
        }
    if "solar water pumps" in text:
        return {
            "stream": q("tender", "buying solar water pumps"),
            "title": q(PUMPS),
            "value_amount": q(45000000, "Estimated budget: RWF 45,000,000"),
            "value_currency": q("RWF", "RWF 45,000,000"),
            "deadline_at": q("2026-12-15", "Submissions close 15 December 2026"),
        }
    raise AssertionError(f"unexpected text sent to the model: {text[:200]}")


@pytest.fixture
def web() -> FakeWeb:
    w = FakeWeb()
    w.add(ORIG, "/robots.txt", httpx.Response(200, text="User-agent: *\nAllow: /\n"))
    w.html(ORIG, "/tenders", LIST_HTML)
    w.html(ORIG, "/notice/101", DETAIL_101)
    w.html(ORIG, "/notice/102", DETAIL_102)
    w.add(
        ORIG,
        "/docs/101.pdf",
        httpx.Response(
            200, content=make_pdf(PDF_101), headers={"content-type": "application/pdf"}
        ),
    )
    w.html(JOBS, "/tenders/solar-pumps", DETAIL_PUMPS)
    w.html(
        JOBS,
        "/tenders/vaccine-transport",
        f"<p>{VACCINES}. Reposted from the issuer.</p>",
    )
    return w


@pytest.fixture
def model():
    return FakeLLM(reply), FakeEmbedder()


def add_source(db, name, **kw) -> Source:
    s = Source(name=name, home_url=kw.pop("home_url"), status="testing", **kw)
    db.add(s)
    db.commit()
    return s


def html_source(db) -> Source:
    return add_source(
        db,
        "Example procurement portal",
        home_url=f"https://{ORIG}",
        streams=["tender"],
        kind="original",
        collector_type="html_list",
        config={
            "list_url": f"https://{ORIG}/tenders",
            "selectors": {
                "item": "ul.notices li",
                "title": "a",
                "link": {"css": "a", "attr": "href"},
                "organisation": ".org",
                "deadline": ".dl",
            },
        },
    )


def search_source(db) -> Source:
    return add_source(
        db,
        "Jobs board via search",
        home_url=f"https://{JOBS}",
        streams=["tender"],
        kind="publisher",
        collector_type="search_query",
        config={"queries": ["tender Rwanda"], "domains": [JOBS], "count": 10},
    )


def by_title(db) -> dict[str, Opportunity]:
    db.expire_all()
    return {o.title: o for o in db.scalars(sa.select(Opportunity))}


def links(db, opp) -> list[OpportunitySource]:
    return list(
        db.scalars(
            sa.select(OpportunitySource)
            .where(OpportunitySource.opportunity_id == opp.id)
            .order_by(OpportunitySource.first_seen)
        )
    )


def docs(db, opp) -> list[Document]:
    return list(
        db.scalars(
            sa.select(Document)
            .where(Document.opportunity_id == opp.id)
            .order_by(Document.url)
        )
    )


def test_html_list_source_end_to_end_then_dedupes(db, web, model, tmp_path):
    llm, emb = model
    src = html_source(db)
    client = make_client(web)
    make_deps = pipeline_deps(tmp_path / "data", llm=llm, embedder=emb)

    run = runner.run_source(
        db, src, client=client, make_deps=make_deps, now=lambda: NOW
    )
    assert (run.status, run.error) == ("succeeded", None)
    assert (run.items_found, run.items_new) == (2, 2)
    assert web.paths(ORIG) == [
        "/robots.txt",
        "/tenders",
        "/notice/101",
        "/docs/101.pdf",
        "/notice/102",
    ]
    assert len(llm.calls) == 2
    # The PDF's text reached the model alongside the listing and detail page.
    assert "Bids close 12 December 2026" in llm.calls[0]["user"]

    opps = by_title(db)
    assert set(opps) == {VACCINES, "Supply of hospital linen"}
    vac = opps[VACCINES]
    assert vac.organisation == ORG and vac.stream == "tender"
    assert kigali_date(vac.deadline_at).isoformat() == "2026-12-12"
    assert vac.status == "open" and vac.visibility == "public"
    assert vac.requirements == ["At least 10 refrigerated trucks"]
    assert vac.fees == "Bid security RWF 500,000"
    assert vac.embedding is not None and not vac.needs_review

    # Evidence: a supporting snippet for every extracted field, deadline included.
    ev = vac.evidence
    assert ev["deadline_at"]["snippet"] == "Bids close 12 December 2026"
    assert ev["deadline_at"]["source_id"] == str(src.id)
    assert ev["title"]["snippet"] == VACCINES.lower()
    assert ev["fees"]["snippet"] == "Bid security RWF 500,000"
    assert ev["requirements"]["snippets"] == ["at least 10 refrigerated trucks"]
    assert ev["_extraction"]["model"] == llm.model
    assert ev["_embedding"]["model"] == emb.model
    assert "_enrich" not in ev  # every fetch succeeded

    # Verification and the UI trust state (spec 6, 12).
    assert vac.verification == "verified_original"
    assert trust_state(vac.verification, vac.evidence) == "confirmed"
    assert ev["_trust"] == "confirmed" and ev["_deadline_conflict"] is False

    # Carrying source: canonical URL (tracking parameter dropped), marked original.
    [link] = links(db, vac)
    assert link.source_id == src.id and link.is_original
    assert link.url == f"https://{ORIG}/notice/101"
    assert link.first_seen == link.last_seen == NOW

    # Documents: detail page and attachment, stored under the data dir with text.
    d_pdf, d_html = docs(db, vac)  # ordered by URL
    assert d_html.url == f"https://{ORIG}/notice/101"
    assert d_pdf.url == f"https://{ORIG}/docs/101.pdf"
    assert "invites sealed bids" in d_html.extracted_text
    assert "track()" not in d_html.extracted_text
    assert "at least 10 refrigerated trucks" in d_pdf.extracted_text
    for d in (d_html, d_pdf):
        path = Path(d.file_path)
        assert path.is_file() and path.is_relative_to(tmp_path / "data" / "documents")
    assert Path(d_pdf.file_path).read_bytes().startswith(b"%PDF-")
    assert len(docs(db, opps["Supply of hospital linen"])) == 1

    # Second run a day later: same notices, so nothing new, no model calls,
    # no refetch of detail pages; last_seen moves, first_seen stays.
    later = NOW + timedelta(days=1)
    again = runner.run_source(
        db, src, client=client, make_deps=make_deps, now=lambda: later
    )
    assert (again.status, again.items_found, again.items_new) == ("succeeded", 2, 0)
    assert len(llm.calls) == 2
    assert web.paths(ORIG)[5:] == ["/tenders"]
    opps = by_title(db)
    assert len(opps) == 2
    [link] = links(db, opps[VACCINES])
    assert (link.first_seen, link.last_seen) == (NOW, later)
    assert len(docs(db, opps[VACCINES])) == 2
    assert db.scalar(sa.select(sa.func.count()).select_from(OpportunitySource)) == 2


BRAVE_RESPONSE = {
    "type": "search",
    "web": {
        "type": "search",
        "results": [
            {
                "title": f"<strong>{VACCINES}</strong>",
                "url": f"https://{JOBS}/tenders/vaccine-transport",
                "description": "Reposted tender notice.",
                "page_age": "2026-11-22T09:00:00",
            },
            {
                "title": PUMPS,
                "url": f"https://{JOBS}/tenders/solar-pumps?utm_source=search",
                "description": "Cooperative union tender for irrigation pumps.",
                "page_age": "2026-11-23T09:00:00",
            },
            {
                "title": "Off-domain result is filtered",
                "url": "https://elsewhere.example/t/1",
            },
        ],
    },
}


def test_search_query_source_flows_into_the_same_pipeline(db, web, model, tmp_path):
    llm, emb = model
    brave_requests = []

    def brave(request: httpx.Request) -> httpx.Response:
        brave_requests.append(request)
        return httpx.Response(200, json=BRAVE_RESPONSE)

    web.add(BRAVE, "/res/v1/web/search", brave)
    client = make_client(web)
    make_deps = pipeline_deps(tmp_path / "data", llm=llm, embedder=emb)

    # The issuer's own notice is already in the catalogue.
    orig = html_source(db)
    runner.run_source(db, orig, client=client, make_deps=make_deps, now=lambda: NOW)
    assert len(llm.calls) == 2

    src = search_source(db)
    later = NOW + timedelta(hours=3)
    run = runner.run_source(
        db,
        src,
        client=client,
        brave_api_key=SecretStr("test-key"),
        make_deps=make_deps,
        now=lambda: later,
    )
    assert (run.status, run.error) == ("succeeded", None)
    assert (run.items_found, run.items_new) == (2, 1)
    [req] = brave_requests
    assert req.headers["x-subscription-token"] == "test-key"
    assert req.url.params["q"] == f"tender Rwanda site:{JOBS}"

    opps = by_title(db)
    assert set(opps) == {VACCINES, "Supply of hospital linen", PUMPS}

    # The repost merged into the original's record: a second, non-original carrying
    # source; still confirmed; no second extraction for it.
    vac = opps[VACCINES]
    vac_links = links(db, vac)
    assert [(lk.source_id, lk.is_original) for lk in vac_links] == [
        (orig.id, True),
        (src.id, False),
    ]
    assert vac_links[1].url == f"https://{JOBS}/tenders/vaccine-transport"
    assert vac_links[1].first_seen == later
    assert vac.verification == "verified_original"
    assert trust_state(vac.verification, vac.evidence) == "confirmed"
    assert len(llm.calls) == 3  # only the pumps notice was extracted

    # The new item: detail page fetched through the guarded client, extracted,
    # unverified (publisher only), with snippets for deadline and amount.
    pumps = opps[PUMPS]
    assert web.paths(JOBS) == ["/robots.txt", "/tenders/solar-pumps"]
    assert "/tenders/vaccine-transport" not in web.paths(JOBS)  # merged: not enriched
    assert pumps.verification == "unverified"
    assert trust_state(pumps.verification, pumps.evidence) == "unconfirmed"
    assert int(pumps.value_amount) == 45_000_000 and pumps.value_currency == "RWF"
    assert (
        pumps.evidence["value_amount"]["snippet"] == "Estimated budget: RWF 45,000,000"
    )
    assert (
        pumps.evidence["deadline_at"]["snippet"] == "Submissions close 15 December 2026"
    )
    assert kigali_date(pumps.deadline_at).isoformat() == "2026-12-15"
    assert pumps.published_at is not None  # from the search result's page_age
    [link] = links(db, pumps)
    assert (
        link.url == f"https://{JOBS}/tenders/solar-pumps"
    )  # tracking parameter dropped
    assert not link.is_original
    [doc] = docs(db, pumps)
    assert "irrigation schemes" in doc.extracted_text
