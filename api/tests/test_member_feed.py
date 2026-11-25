"""Member API: /feed, /opportunities/{id}, state, note, /shortlist
(docs/api-contract.md section 2)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from blackkite.db.models import ChangeEvent, Document, UserOpportunity, UserSourceMute
from blackkite.routes.member import now_utc
from tests import factories as f
from tests.conftest import make_user, sign_in
from tests.factories import NOW, kigali


@pytest.fixture
def frozen(app):
    app.dependency_overrides[now_utc] = lambda: NOW
    return app


@pytest.fixture
def login(frozen, outbox) -> Iterator[Callable[[str], TestClient]]:
    clients: list[TestClient] = []

    def make(email: str) -> TestClient:
        c = TestClient(frozen, base_url="https://testserver")
        c.__enter__()
        clients.append(c)
        return sign_in(c, outbox, email)

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def ana(db):
    u = make_user(db, "ana@example.com")
    u.name = "Ana Uwase"
    db.commit()
    return u


def _items(client: TestClient, **params) -> list[dict]:
    r = client.get("/api/feed", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _ids(client: TestClient, **params) -> list[str]:
    return [i["id"] for i in _items(client, **params)]


_FIT_WORDS = {
    "strong": "Strong fit",
    "good": "Good fit",
    "possible": "Possible fit",
    "not-scored": "Not scored",
}


def _subtitle(item: dict) -> str:
    """web/src/lib/subtitle.ts rowSubtitle, desktop, tender/funding branch."""
    top = item.get("topFlag")
    parts = [
        _FIT_WORDS.get(item["fit"]) if item["fit"] else None,
        top[0].lower() + top[1:] if top else item["organisation"],
    ]
    return " · ".join(p for p in parts if p)


# --- auth -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/feed"),
        ("get", "/api/shortlist"),
        ("get", f"/api/opportunities/{uuid.uuid4()}"),
        ("put", f"/api/opportunities/{uuid.uuid4()}/state"),
        ("put", f"/api/opportunities/{uuid.uuid4()}/note"),
    ],
)
def test_every_route_needs_a_session(client, method, path):
    kw = {"json": {"state": "saved", "note": "x"}} if method == "put" else {}
    r = getattr(client, method)(path, **kw)
    assert r.status_code == 401


# --- the board's items, rebuilt from rows ------------------------------------------------


def _wfp(db, user):
    jir = f.source(db, "Job in Rwanda, tenders", publisher="Job in Rwanda")
    opp = f.opportunity(
        db,
        "Logistics, transport and warehousing support",
        organisation="World Food Programme",
        organisation_short="WFP",
        location="Kigali",
        deadline_at=kigali(2026, 11, 30),
        published_at=kigali(2026, 11, 9, 9),
        verification="unverified",
        evidence={"_trust": "unconfirmed"},
    )
    f.link(db, opp, jir, "https://www.jobinrwanda.com/jobs/tender")
    ironji = f.profile(db, user, "Ironji-Trade")
    f.score(
        db,
        user,
        opp,
        ironji,
        88,
        fit_word="strong",
        reasons=[
            "It asks for transport, warehousing and logistics support, which you offer.",
            "It is in Rwanda, where your network of more than 1,000 trucks operates.",
        ],
        flags=[
            {
                "code": "owned_fleet",
                "label": "May require owned fleet",
                "quote": "copies of vehicle logbooks",
                "to_check": "WFP's transport call in May asked for vehicle logbooks, "
                "so this one may require an owned fleet.",
            }
        ],
    )
    db.commit()
    return opp


def test_wfp_item_matches_the_reference_fixture(db, ana, login):
    opp = _wfp(db, ana)
    c = login(ana.email)
    body = c.get("/api/feed").json()
    assert body["user"] == {"name": "Ana"}
    assert body["digest"] == {"channel": "email"}
    [item] = body["items"]
    # web/src/fixtures/reference.ts, item wfp-logistics, word for word: Strong with
    # a flag, so no topFlag (contract section 2); the flag shows as To check.
    assert "topFlag" not in item
    assert _subtitle(item) == "Strong fit · World Food Programme"
    assert item == {
        "id": str(opp.id),
        "stream": "tender",
        "title": "Logistics, transport and warehousing support",
        "organisation": "World Food Programme",
        "organisationShort": "WFP",
        "fit": "strong",
        "deadline": "2026-11-30",
        "detail": {
            "profile": "Ironji-Trade",
            "location": "Kigali",
            "reasons": [
                "It asks for transport, warehousing and logistics support, which you offer.",
                "It is in Rwanda, where your network of more than 1,000 trucks operates.",
            ],
            "toCheck": "To check: WFP's transport call in May asked for vehicle "
            "logbooks, so this one may require an owned fleet.",
            "trust": {
                "state": "unconfirmed",
                "desktop": "Found on Job in Rwanda, posted 9 Nov. We have not matched it "
                "to a notice on WFP's own site yet, so check the date there before "
                "you act.",
                "phone": "Found on Job in Rwanda, posted 9 Nov. Check the date on WFP's "
                "own site before you act.",
            },
            "originalUrl": "https://www.jobinrwanda.com/jobs/tender",
        },
    }


def test_developpp_item_matches_the_reference_fixture(db, ana, login):
    org = f.source(db, "develoPPP site", kind="original", publisher="develoPPP")
    opp = f.opportunity(
        db,
        "develoPPP Ventures, cohort 6",
        stream="funding",
        organisation="develoPPP",
        location="Rwanda",
        deadline_at=kigali(2026, 12, 31),
        verification="verified_original",
        evidence={"_trust": "confirmed"},
    )
    f.link(db, opp, org, "https://www.developpp.de/", is_original=True)
    ironji = f.profile(db, ana, "Ironji-Trade")
    f.score(
        db,
        ana,
        opp,
        ironji,
        70,
        fit_word="good",
        reasons=[
            "It backs growing companies in Africa that want to scale a proven business."
        ],
        flags=[
            {
                "code": "model_other",
                "label": "Needs matching funds",
                "quote": "matching funds",
                "to_check": "it needs matching funds from your side.",
            }
        ],
    )
    db.commit()
    [item] = _items(login(ana.email))
    # web/src/fixtures/reference.ts, item developpp-6, word for word except two
    # things: hideOnPhone is web-only (decision 4), and the fixture's trust copy
    # says "the programme’s" where the API fills in the source's publisher.
    trust = item["detail"].pop("trust")
    assert trust == {
        "state": "confirmed",
        "desktop": "Matched to the call on develoPPP’s own site.",
        "phone": "Matched to the call on develoPPP’s own site.",
    }
    assert item == {
        "id": str(opp.id),
        "stream": "funding",
        "title": "develoPPP Ventures, cohort 6",
        "organisation": "develoPPP",
        "fit": "good",
        "topFlag": "Needs matching funds",
        "deadline": "2026-12-31",
        "detail": {
            "profile": "Ironji-Trade",
            "location": "Rwanda",
            "reasons": [
                (
                    "It backs growing companies in Africa that want to scale a "
                    "proven business."
                )
            ],
            "toCheck": "To check: it needs matching funds from your side.",
            "originalUrl": "https://www.developpp.de/",
        },
    }
    assert _subtitle(item) == "Good fit · needs matching funds"


@pytest.mark.parametrize(
    ("word", "flags", "top"),
    [
        ("strong", [{"label": "Value unknown"}], None),
        ("good", [{"label": "Value unknown"}], "Value unknown"),
        ("good", [], None),
        ("possible", [{"label": "Value unknown"}], None),
    ],
)
def test_top_flag_only_for_good_fit(db, ana, login, word, flags, top):
    src = f.source(db, "Src")
    opp = f.opportunity(db, "X", deadline_at=kigali(2026, 12, 10))
    f.link(db, opp, src)
    f.score(db, ana, opp, f.profile(db, ana, "P"), 70, fit_word=word, flags=flags)
    db.commit()
    [item] = _items(login(ana.email))
    assert item["fit"] == word and item.get("topFlag") == top


def test_event_item_matches_the_reference_fixture(db, ana, login):
    org = f.source(
        db, "ABH site", kind="original", publisher="Africa's Business Heroes"
    )
    opp = f.opportunity(
        db,
        "ABH Summit and Grand Finale",
        stream="event",
        organisation="Africa's Business Heroes",
        location="Kigali Convention Centre",
        event_start=kigali(2026, 12, 1, 9),
        event_end=kigali(2026, 12, 2, 18),
        tags=["sector:startups and investors", "service:events"],
        verification="verified_original",
        evidence={"_trust": "confirmed"},
    )
    f.link(db, opp, org, "https://africabusinessheroes.org/", is_original=True)
    personal = f.profile(
        db, ana, "Personal", "personal", streams=["investment", "event"]
    )
    f.score(
        db,
        ana,
        opp,
        personal,
        60,
        fit_word=None,
        reasons=["It is about startups and investors, one of your event topics."],
    )
    db.commit()
    [item] = _items(login(ana.email))
    assert item == {
        "id": str(opp.id),
        "stream": "event",
        "title": "ABH Summit and Grand Finale",
        "organisation": "Africa's Business Heroes",
        "fit": None,
        "topic": "Startups and investors",
        "venue": "Kigali Convention Centre",
        "deadline": None,
        "eventDates": {"start": "2026-12-01", "end": "2026-12-02"},
        "detail": {
            "profile": "Personal",
            "location": "Kigali Convention Centre",
            "reasons": [
                "It is about startups and investors, one of your event topics."
            ],
            "trust": {
                "state": "confirmed",
                "desktop": "Dates and venue match the organiser’s own event page.",
                "phone": "Dates and venue match the organiser’s own page.",
            },
            "originalUrl": "https://africabusinessheroes.org/",
        },
    }


def test_investment_item_has_note_and_no_deadline_wording(db, ana, login):
    rse = f.source(db, "RSE", kind="original", publisher="RSE")
    opp = f.opportunity(
        db,
        "Five-year treasury bond",
        stream="investment",
        organisation="National Bank of Rwanda",
        value_note="trading on the RSE",
        location="Rwanda Stock Exchange",
        verification="verified_original",
        evidence={"_trust": "confirmed"},
    )
    f.link(db, opp, rse, "https://www.rse.rw/", is_original=True)
    db.commit()
    [item] = _items(login(ana.email))
    assert item["fit"] is None
    assert item["note"] == "trading on the RSE"
    assert item["deadline"] is None and item["noDeadlineText"] == "No deadline"
    assert item["detail"]["trust"]["desktop"] == "Listed on RSE’s own site."
    assert item["detail"]["reasons"] == []
    assert "profile" not in item["detail"]


def test_confirmed_funding_and_conflict_copy(db, ana, login):
    ncst = f.source(db, "NCST calls", kind="original", publisher="NCST")
    board = f.source(db, "Board", publisher="Opportunity Board")
    call = f.opportunity(
        db,
        "Transition to Scale research and innovation call",
        stream="funding",
        organisation="National Council for Science and Technology",
        organisation_short="NCST",
        deadline_at=kigali(2026, 12, 7),
        evidence={"_trust": "confirmed"},
        verification="verified_original",
    )
    f.link(db, call, ncst, "https://www.ncst.gov.rw/", is_original=True)
    closed_conflict = f.opportunity(
        db,
        "Invitation for bids",
        deadline_at=kigali(2026, 11, 26),
        evidence={"_trust": "conflict", "_deadline_conflict": True},
        verification="verified_original",
    )
    f.link(db, closed_conflict, ncst, "https://umucyo.example/1", is_original=True)
    f.link(db, closed_conflict, board, "https://board.example/1")
    db.commit()
    by_id = {i["id"]: i for i in _items(login(ana.email))}
    assert by_id[str(call.id)]["fit"] == "not-scored"
    assert by_id[str(call.id)]["detail"]["trust"] == {
        "state": "confirmed",
        "desktop": "Matched to the call on NCST’s own site.",
        "phone": "Matched to the call on NCST’s own site.",
    }
    assert by_id[str(closed_conflict.id)]["detail"]["trust"]["desktop"] == (
        "Two sources give different closing dates; the original says 26 Nov."
    )


def test_optional_fields_are_omitted_not_null(db, ana, login):
    src = f.source(db, "Src")
    opp = f.opportunity(db, "Bare", organisation=None)
    f.link(db, opp, src)
    db.commit()
    [item] = _items(login(ana.email))
    assert item["organisation"] == ""
    for key in ("organisationShort", "topFlag", "topic", "venue", "note", "eventDates"):
        assert key not in item
    assert item["noDeadlineText"] == "No deadline stated"
    assert "toCheck" not in item["detail"] and "location" not in item["detail"]
    assert item["fit"] == "not-scored" and item["deadline"] is None


# --- scores --------------------------------------------------------------------------------


def test_best_profile_and_hard_filtered_rows(db, ana, login):
    src = f.source(db, "Src")
    a = f.profile(db, ana, "A")
    b = f.profile(db, ana, "B")
    both = f.opportunity(db, "Both", deadline_at=kigali(2026, 12, 10))
    f.link(db, both, src)
    f.score(db, ana, both, a, 50, fit_word="possible")
    f.score(
        db, ana, both, b, 90, fit_word="good", flags=[{"label": "Needs matching funds"}]
    )
    gone = f.opportunity(db, "Filtered", deadline_at=kigali(2026, 12, 10))
    f.link(db, gone, src)
    f.score(db, ana, gone, a, 99, hard_filtered="ineligible")
    # Highest raw score is filtered; the shown profile is the best unfiltered one.
    mixed = f.opportunity(db, "Mixed", deadline_at=kigali(2026, 12, 11))
    f.link(db, mixed, src)
    f.score(db, ana, mixed, a, 95, hard_filtered="below_min_value")
    f.score(db, ana, mixed, b, 40, fit_word="possible")
    db.commit()
    c = login(ana.email)
    items = {i["title"]: i for i in _items(c)}
    assert set(items) == {"Both", "Mixed"}
    assert items["Both"]["detail"]["profile"] == "B"
    assert items["Both"]["fit"] == "good"
    assert items["Both"]["topFlag"] == "Needs matching funds"
    assert items["Mixed"]["detail"]["profile"] == "B"
    # The profile filter shows that profile's view of the item.
    only_a = {i["title"]: i for i in _items(c, profile=str(a.id))}
    assert set(only_a) == {"Both"}
    assert only_a["Both"]["fit"] == "possible"
    # The detail page still opens a filtered item, with no fit shown.
    r = c.get(f"/api/opportunities/{gone.id}")
    assert r.status_code == 200 and r.json()["fit"] is None


def test_inactive_profile_scores_are_ignored(db, ana, login):
    src = f.source(db, "Src")
    p = f.profile(db, ana, "Old")
    p.active = False
    opp = f.opportunity(db, "X")
    f.link(db, opp, src)
    f.score(db, ana, opp, p, 90, fit_word="strong")
    db.commit()
    [item] = _items(login(ana.email))
    assert item["fit"] == "not-scored" and "profile" not in item["detail"]


def test_closing_soonest_first(db, ana, login):
    src = f.source(db, "Src")
    later = f.opportunity(db, "Later", deadline_at=kigali(2026, 12, 23))
    undated = f.opportunity(db, "Undated")
    soon = f.opportunity(db, "Soon", deadline_at=kigali(2026, 11, 30))
    event = f.opportunity(db, "Event", stream="event", event_start=kigali(2026, 12, 1))
    expired = f.opportunity(db, "Expired", deadline_at=kigali(2026, 11, 23))
    passed_today = f.opportunity(db, "Passed", deadline_at=NOW - timedelta(hours=1))
    for o in (later, undated, soon, event, expired, passed_today):
        f.link(db, o, src)
    db.commit()
    assert [i["title"] for i in _items(login(ana.email))] == [
        "Soon",
        "Event",
        "Later",
        "Undated",
    ]


# --- visibility and isolation -----------------------------------------------------------


def test_feed_hides_testing_retired_and_other_users_private_items(db, ana, login):
    admin = make_user(db, "admin@example.com", role="admin")
    active = f.source(db, "Active")
    testing = f.source(db, "Testing", status="testing")
    retired = f.source(db, "Retired", status="retired")
    paused = f.source(db, "Paused", status="paused")
    shown = f.opportunity(db, "Shown")
    f.link(db, shown, active)
    hidden_testing = f.opportunity(db, "Testing only")
    f.link(db, hidden_testing, testing)
    hidden_retired = f.opportunity(db, "Retired only")
    f.link(db, hidden_retired, retired)
    by_paused = f.opportunity(db, "Paused keeps")
    f.link(db, by_paused, paused)
    f.opportunity(db, "No source")
    theirs = f.opportunity(
        db, "Admin's private", visibility="private", owner_user_id=admin.id
    )
    mine = f.opportunity(
        db, "Ana's private", visibility="private", owner_user_id=ana.id
    )
    db.commit()
    assert sorted(i["title"] for i in _items(login(ana.email))) == [
        "Ana's private",
        "Paused keeps",
        "Shown",
    ]
    # Admins get the member rule in member routes too: testing items stay out.
    assert sorted(i["title"] for i in _items(login(admin.email))) == [
        "Admin's private",
        "Paused keeps",
        "Shown",
    ]
    assert mine.id and theirs.id


def test_no_route_touches_another_users_private_item(db, ana, login):
    other = make_user(db, "ben@example.com")
    theirs = f.opportunity(
        db, "Ben's private", visibility="private", owner_user_id=other.id
    )
    testing = f.source(db, "Testing", status="testing")
    hidden = f.opportunity(db, "Testing only")
    f.link(db, hidden, testing)
    db.commit()
    c = login(ana.email)
    for opp in (theirs, hidden):
        assert c.get(f"/api/opportunities/{opp.id}").status_code == 404
        for state in ("saved", "dismissed", "acting", "done"):
            r = c.put(f"/api/opportunities/{opp.id}/state", json={"state": state})
            assert r.status_code == 404
        r = c.put(f"/api/opportunities/{opp.id}/note", json={"note": "mine now"})
        assert r.status_code == 404
    assert c.get(f"/api/opportunities/{uuid.uuid4()}").status_code == 404
    assert db.scalar(sa.select(sa.func.count()).select_from(UserOpportunity)) == 0
    # Ben still sees his own item, with no trace of Ana.
    b = login(other.email)
    assert [i["title"] for i in _items(b)] == ["Ben's private"]
    r = b.get(f"/api/opportunities/{theirs.id}")
    assert r.status_code == 200
    assert r.json()["detail"]["note"] is None
    assert r.json()["detail"]["trust"]["desktop"] == (
        "You added this item yourself, so nobody else has checked it."
    )


def test_states_and_notes_are_per_user(db, ana, login):
    ben = make_user(db, "ben@example.com")
    src = f.source(db, "Src")
    opp = f.opportunity(db, "Shared", deadline_at=kigali(2026, 12, 5))
    f.link(db, opp, src)
    db.commit()
    a, b = login(ana.email), login(ben.email)
    r = a.put(
        f"/api/opportunities/{opp.id}/state",
        json={"state": "dismissed", "dismissReason": "too far"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "dismissed" and r.json()["dismissReason"] == "too far"
    a.put(f"/api/opportunities/{opp.id}/note", json={"note": "  call Monday "})
    assert _items(a) == []
    assert [i["id"] for i in _items(a, state="dismissed")] == [str(opp.id)]
    # Ben's view is untouched.
    assert [i["id"] for i in _items(b)] == [str(opp.id)]
    detail_b = b.get(f"/api/opportunities/{opp.id}").json()["detail"]
    assert detail_b["note"] is None and detail_b["state"] == "unseen"
    detail_a = a.get(f"/api/opportunities/{opp.id}").json()["detail"]
    assert detail_a["note"] == "call Monday"
    assert detail_a["state"] == "dismissed" and detail_a["dismissReason"] == "too far"
    # Moving off dismissed drops the reason; the note stays.
    r = a.put(f"/api/opportunities/{opp.id}/state", json={"state": "saved"})
    assert r.json() == {
        "opportunityId": str(opp.id),
        "state": "saved",
        "dismissReason": None,
        "note": "call Monday",
        "updatedAt": r.json()["updatedAt"],
    }


def test_state_body_is_validated(db, ana, login):
    src = f.source(db, "Src")
    opp = f.opportunity(db, "X")
    f.link(db, opp, src)
    db.commit()
    c = login(ana.email)
    assert (
        c.put(f"/api/opportunities/{opp.id}/state", json={"state": "liked"}).status_code
        == 422
    )
    assert (
        c.put(
            f"/api/opportunities/{opp.id}/state", json={"state": "saved", "x": 1}
        ).status_code
        == 422
    )
    assert (
        c.put(
            f"/api/opportunities/{opp.id}/note", json={"note": "x" * 5001}
        ).status_code
        == 422
    )


def test_shortlist_is_saved_and_acting_soonest_first(db, ana, login):
    src = f.source(db, "Src")
    rows = {}
    for title, deadline, st in [
        ("Acting later", kigali(2026, 12, 20), "acting"),
        ("Saved soon", kigali(2026, 11, 27), "saved"),
        ("Saved closed", kigali(2026, 11, 20), "saved"),
        ("Done", kigali(2026, 11, 28), "done"),
        ("Dismissed", kigali(2026, 11, 28), "dismissed"),
    ]:
        o = f.opportunity(db, title, deadline_at=deadline)
        f.link(db, o, src)
        f.state(db, ana, o, st)
        rows[title] = o
    db.commit()
    r = login(ana.email).get("/api/shortlist")
    assert [i["title"] for i in r.json()] == [
        "Saved soon",
        "Acting later",
        "Saved closed",
    ]
    assert r.json()[2]["fit"] is None  # closed


# --- filters ------------------------------------------------------------------------------


def test_filters(db, ana, login):
    one = f.source(db, "One", kind="original")
    two = f.source(db, "Two")
    t = f.opportunity(
        db,
        "Tender soon",
        deadline_at=kigali(2026, 11, 29),
        verification="verified_original",
    )
    f.link(db, t, one, is_original=True)
    fu = f.opportunity(
        db, "Funding later", stream="funding", deadline_at=kigali(2027, 1, 30)
    )
    f.link(db, fu, two)
    ev = f.opportunity(
        db, "Event soon", stream="event", event_start=kigali(2026, 11, 28)
    )
    f.link(db, ev, two)
    undated = f.opportunity(db, "Undated")
    f.link(db, undated, two)
    db.commit()
    c = login(ana.email)
    assert _ids(c, stream="funding") == [str(fu.id)]
    assert _ids(c, window=7) == [str(ev.id), str(t.id)]
    assert _ids(c, verification="verified_original") == [str(t.id)]
    assert _ids(c, source=str(one.id)) == [str(t.id)]
    assert set(_ids(c, state="unseen")) == {
        str(t.id),
        str(fu.id),
        str(ev.id),
        str(undated.id),
    }
    assert c.get("/api/feed", params={"stream": "jobs"}).status_code == 422
    assert c.get("/api/feed", params={"verification": "confirmed"}).status_code == 422


def test_items_only_from_muted_sources_leave_the_feed(db, ana, login):
    muted = f.source(db, "Muted")
    other = f.source(db, "Other")
    only_muted = f.opportunity(db, "Only muted")
    f.link(db, only_muted, muted)
    both = f.opportunity(db, "Both")
    f.link(db, both, muted)
    f.link(db, both, other)
    db.add(UserSourceMute(user_id=ana.id, source_id=muted.id))
    db.commit()
    c = login(ana.email)
    assert [i["title"] for i in _items(c)] == ["Both"]
    assert c.get(f"/api/opportunities/{only_muted.id}").status_code == 200


# --- opportunity page -----------------------------------------------------------------------


def test_opportunity_detail(db, ana, login):
    opp = _wfp(db, ana)
    testing = f.source(db, "Hidden testing", status="testing", kind="original")
    f.link(db, opp, testing, "https://hidden.example/x", is_original=True)
    opp.eligibility = "Registered transport companies"
    opp.requirements = ["Vehicle logbooks"]
    opp.value_amount = 12000000
    opp.value_currency = "RWF"
    opp.evidence = {
        **opp.evidence,
        "eligibility": {"snippet": "open to registered transport companies"},
        "deadline_at": {"snippet": "Closing date: 30 November 2026"},
        "value_amount": {"snippet": "FRW 12,000,000"},
        "requirements": {"snippets": ["copies of vehicle logbooks"]},
    }
    db.add(
        Document(
            opportunity_id=opp.id,
            url="https://x.example/files/ToR%20WFP.pdf",
            extracted_text="SECRET FULL TEXT",
        )
    )
    db.add(
        Document(
            opportunity_id=opp.id,
            url="https://x.example/a",
            file_path="/data/d/notice.pdf",
        )
    )
    db.add(
        ChangeEvent(
            opportunity_id=opp.id,
            field="deadline_at",
            old="2026-11-27T15:00:00+00:00",
            new="2026-11-30T15:00:00+00:00",
            at=NOW - timedelta(days=1),
        )
    )
    db.add(
        ChangeEvent(
            opportunity_id=opp.id,
            field="source_deadline",
            old={"source_id": str(testing.id), "value": "a"},
            new={"source_id": str(testing.id), "value": "b"},
            at=NOW,
        )
    )
    f.state(db, ana, opp, "saved", note="Ask about subcontracting")
    db.commit()
    r = login(ana.email).get(f"/api/opportunities/{opp.id}")
    assert r.status_code == 200
    body = r.json()
    d = body["detail"]
    assert body["fit"] == "strong" and d["profile"] == "Ironji-Trade"
    assert d["note"] == "Ask about subcontracting" and d["state"] == "saved"
    # Only the member-visible source; the testing original is not listed or used.
    assert [s["name"] for s in d["sources"]] == ["Job in Rwanda, tenders"]
    assert d["sources"][0]["isOriginal"] is False
    assert d["originalUrl"] == "https://www.jobinrwanda.com/jobs/tender"
    assert d["documents"] == [{"name": "ToR WFP.pdf"}, {"name": "notice.pdf"}]
    assert "SECRET" not in r.text
    fields = {x["name"]: x for x in d["fields"]}
    assert fields["eligibility"] == {
        "name": "eligibility",
        "value": "Registered transport companies",
        "snippet": "open to registered transport companies",
    }
    assert fields["deadlineAt"]["snippet"] == "Closing date: 30 November 2026"
    assert fields["valueAmount"] == {
        "name": "valueAmount",
        "value": "12000000.00",
        "snippet": "FRW 12,000,000",
    }
    assert fields["requirements"]["snippets"] == ["copies of vehicle logbooks"]
    assert "snippet" not in fields["organisation"]
    # The change from a hidden source is not shown.
    assert [c["field"] for c in d["changes"]] == ["deadline_at"]


def test_best_profile_ignores_a_higher_inactive_profile(db, ana, login):
    src = f.source(db, "Src")
    live = f.profile(db, ana, "Live")
    old = f.profile(db, ana, "Old")
    old.active = False
    opp = f.opportunity(db, "X", deadline_at=kigali(2026, 12, 10))
    f.link(db, opp, src)
    f.score(db, ana, opp, live, 40, fit_word="possible")
    f.score(db, ana, opp, old, 95, fit_word="good", flags=[{"label": "Value unknown"}])
    db.commit()
    c = login(ana.email)
    [item] = _items(c)
    assert item["fit"] == "possible" and item["detail"]["profile"] == "Live"
    assert "topFlag" not in item
    assert c.get(f"/api/opportunities/{opp.id}").json()["detail"]["profile"] == "Live"
    assert _items(c, profile=str(old.id)) == []
