"""Match + score end to end against Postgres, with the spec 7.1 seed profiles."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from blackkite.db.models import Profile, UserOpportunityScore, UserSourceMute
from blackkite.llm.client import LLMError
from blackkite.scoring.service import (
    NO_MODEL_REASON,
    backfill_profile,
    score_new_opportunities,
    score_user,
)
from tests.scoring.conftest import (
    BowEmbedder,
    FakeScoreLLM,
    days,
    deps,
    flag_codes,
    judgement,
    now,
    row,
)

COLD = "Provision of cold chain transport services for vaccines"
CONTRACT_KEYS = {
    "version",
    "components",
    "fit_confidence",
    "eligibility_confidence",
    "fit_word",
    "reasons",
    "flags",
    "provisional",
    "hard_filtered",
    "model",
    "prompt_version",
    "scored_at",
}
WEIGHTS = {"fit": 40, "eligibility": 20, "value": 15, "time": 15, "source": 10}


def _check_contract(r: UserOpportunityScore) -> None:
    b = r.score_breakdown
    assert set(b) == CONTRACT_KEYS
    assert b["version"] == 1
    assert set(b["components"]) == set(WEIGHTS)
    for k, v in b["components"].items():
        assert 0 <= v <= WEIGHTS[k]
    assert 0 <= b["fit_confidence"] <= 1 and 0 <= b["eligibility_confidence"] <= 1
    assert b["fit_word"] in ("strong", "good", "possible", None)
    assert isinstance(b["reasons"], list) and b["reasons"]
    for f in b["flags"]:
        assert set(f) == {"code", "label", "quote", "to_check"}
    assert isinstance(b["provisional"], bool)
    assert 0 <= r.score <= 100
    assert r.score_reason == b["reasons"][0]
    assert abs(r.score - sum(b["components"].values())) <= 1


def test_strong_tender_with_quoted_reason(db, profiles, make_opp):
    o = make_opp(
        COLD,
        tags=["service:cold chain transport", "sector:health"],
        value_amount=40_000_000,
        value_currency="RWF",
        requirements=["Experience in temperature-controlled transport of medicines."],
        deadline_at=days(30),
    )
    llm = FakeScoreLLM(judgement(quote="temperature-controlled transport of medicines"))
    stats = score_user(db, profiles["Ironji-Trade"].user_id, deps=deps(llm))
    db.commit()
    r = row(db, profiles["Ironji-Trade"], o)
    _check_contract(r)
    b = r.score_breakdown
    assert b["fit_word"] == "strong" and b["flags"] == [] and b["hard_filtered"] is None
    assert "temperature-controlled transport of medicines" in r.score_reason
    assert b["model"] == "fake-score-1" and b["prompt_version"] == "score-v1"
    assert b["provisional"] is False
    # AI lab (also tender) gets its own row, marked provisional.
    ai = row(db, profiles["AI lab"], o)
    _check_contract(ai)
    assert ai.score_breakdown["provisional"] is True
    # Personal does not follow tenders.
    p = row(db, profiles["Personal"], o)
    _check_contract(p)
    assert p.score_breakdown["hard_filtered"] == "stream_not_selected"
    assert p.score == 0 and p.score_breakdown["fit_word"] is None
    assert stats.llm_calls == len(llm.calls) >= 1
    assert (
        "<profile>" in llm.calls[0]["user"]
        and llm.calls[0]["tool"] == "record_judgement"
    )


def test_unsupported_quote_is_rejected(db, profiles, make_opp):
    o = make_opp(
        COLD,
        tags=["service:cold chain transport"],
        value_amount=9e6,
        value_currency="RWF",
    )
    llm = FakeScoreLLM(
        judgement(
            fit=0.95,
            elig=0.95,
            quote="bidders must hold ISO 22000",
            reason='It needs "bidders must hold ISO 22000".',
        )
    )
    score_user(db, profiles["Ironji-Trade"].user_id, deps=deps(llm))
    db.commit()
    r = row(db, profiles["Ironji-Trade"], o)
    b = r.score_breakdown
    assert "ISO 22000" not in r.score_reason
    assert b["fit_confidence"] <= 0.5 and b["eligibility_confidence"] <= 0.5
    assert b["fit_word"] == "possible"


def test_unsupported_model_flags_are_dropped(db, profiles, make_opp):
    o = make_opp(
        COLD,
        tags=["service:cold chain transport"],
        value_amount=9e6,
        value_currency="RWF",
        requirements=["Three similar contracts completed in the last five years."],
    )
    flags = [
        {
            "kind": "experience",
            "quote": "Three similar contracts completed",
            "to_check": "Check you have three.",
        },
        {"kind": "documents", "quote": "an invented requirement", "to_check": "x"},
    ]
    score_user(
        db,
        profiles["Ironji-Trade"].user_id,
        deps=deps(FakeScoreLLM(judgement(flags=flags))),
    )
    db.commit()
    b = row(db, profiles["Ironji-Trade"], o).score_breakdown
    assert [(f["code"], f["label"]) for f in b["flags"]] == [
        ("model_experience", "Check experience")
    ]
    # Flags do not lower the word (contract section 1, revised): strong with a note.
    assert b["fit_word"] == "strong"


def test_71_flags_end_to_end(db, profiles, make_opp, make_source):
    umucyo = make_source(home_url="https://umucyo.gov.rw", name="Umucyo")
    o = make_opp(
        "Transport of maize from Musanze to Kigali warehouses",
        source=umucyo,
        tags=["service:freight transport"],
        requirements=[
            "Copies of vehicle logbooks for every truck proposed.",
            "A valid transport operator licence.",
        ],
    )
    llm = FakeScoreLLM(judgement(quote="Copies of vehicle logbooks"))
    score_user(db, profiles["Ironji-Trade"].user_id, deps=deps(llm))
    db.commit()
    r = row(db, profiles["Ironji-Trade"], o)
    _check_contract(r)
    flags = {f["code"]: f for f in r.score_breakdown["flags"]}
    assert flag_codes(r) == [
        "owned_fleet",
        "transport_licence",
        "umucyo_registration",
        "value_unknown",
    ]
    assert flags["owned_fleet"]["label"] == "May require owned fleet"
    assert "vehicle logbooks" in flags["owned_fleet"]["quote"]
    assert flags["transport_licence"]["label"] == "Requires transport licence"
    assert "transport operator licence" in flags["transport_licence"]["quote"]
    assert flags["umucyo_registration"]["label"] == "Needs Umucyo supplier registration"
    assert flags["value_unknown"]["label"] == "Value unknown"
    assert r.score_breakdown["hard_filtered"] is None
    # Model says fit 0.85, eligibility 0.8: strong even with four flags (the WFP
    # board shows Strong with a "To check" note).
    assert r.score_breakdown["fit_word"] == "strong"
    # The model was told which rule flags were already raised.
    assert "May require owned fleet" in llm.calls[0]["user"]


def test_hard_filters_stored(db, owner, profiles, make_opp, make_source):
    low = make_opp(
        COLD, tags=["service:cold chain"], value_amount=3_000_000, value_currency="RWF"
    )
    abroad = make_opp(
        COLD + " in Nairobi", tags=["service:cold chain"], location="Nairobi, Kenya"
    )
    ngo = make_opp(
        "Grant for cold chain innovation",
        stream="funding",
        eligibility="Open only to registered NGOs.",
    )
    muted_src = make_source()
    muted = make_opp(COLD + " (muted)", source=muted_src, tags=["service:cold chain"])
    db.add(UserSourceMute(user_id=owner.id, source_id=muted_src.id))
    db.commit()
    llm = FakeScoreLLM(judgement())
    score_user(db, owner.id, deps=deps(llm))
    db.commit()
    ironji = profiles["Ironji-Trade"]
    got = {
        o.title: row(db, ironji, o).score_breakdown["hard_filtered"]
        for o in (low, abroad, ngo, muted)
    }
    assert got == {
        low.title: "below_min_value",
        abroad.title: "outside_rwanda",
        ngo.title: "ineligible",
        muted.title: "muted_source_only",
    }
    assert llm.calls == []  # filtered pairs never reach the model
    for o in (low, abroad, ngo, muted):
        _check_contract(row(db, ironji, o))


def test_events_and_investments_rank_on_time_and_source_without_model(
    db, profiles, make_opp, make_source
):
    agg = make_source(kind="aggregator", streams=("event",))
    good = make_opp(
        "AI and fintech summit Kigali",
        stream="event",
        event_start=days(30),
        tags=["sector:fintech"],
    )
    weak = make_opp(
        "Tech meetup Kigali",
        stream="event",
        source=agg,
        event_start=days(1),
        verification="aggregator_only",
        evidence={"_trust": "unconfirmed"},
    )
    bond = make_opp(
        "Treasury bond issue FXD 2026/5",
        stream="investment",
        subtype="treasury bond",
        organisation="National Bank of Rwanda",
        organisation_short="BNR",
        deadline_at=days(12),
    )
    llm = FakeScoreLLM(judgement())
    score_user(db, profiles["Personal"].user_id, deps=deps(llm))
    db.commit()
    personal = profiles["Personal"]
    rg, rw, rb = (row(db, personal, o) for o in (good, weak, bond))
    for r in (rg, rw, rb):
        _check_contract(r)
        assert r.score_breakdown["fit_word"] is None
        assert r.score_breakdown["model"] is None
    assert rg.score > rw.score
    assert (
        rg.score_breakdown["components"]["time"]
        > rw.score_breakdown["components"]["time"]
    )
    assert (
        rg.score_breakdown["components"]["source"]
        > rw.score_breakdown["components"]["source"]
    )
    assert rb.score_reason.startswith("Treasury bond from BNR, closing ")
    # No model call for events or investments, for any profile.
    assert all("AI and fintech summit" not in c["user"] for c in llm.calls)
    assert all("Treasury bond" not in c["user"] for c in llm.calls)


def test_no_model_key_scores_rules_only(db, profiles, make_opp):
    o = make_opp(
        COLD,
        tags=["service:cold chain transport"],
        value_amount=9e6,
        value_currency="RWF",
    )
    stats = score_user(db, profiles["Ironji-Trade"].user_id, deps=deps(llm=None))
    db.commit()
    r = row(db, profiles["Ironji-Trade"], o)
    _check_contract(r)
    b = r.score_breakdown
    assert r.score_reason == NO_MODEL_REASON == b["reasons"][0]
    assert b["model"] is None and b["prompt_version"] is None
    assert b["fit_word"] in ("possible", None)
    assert stats.rules_only >= 1


def test_model_error_falls_back_and_retries_next_run(db, profiles, make_opp):
    o = make_opp(
        COLD,
        tags=["service:cold chain transport"],
        value_amount=9e6,
        value_currency="RWF",
    )
    uid = profiles["Ironji-Trade"].user_id
    stats = score_user(db, uid, deps=deps(FakeScoreLLM(error=LLMError("boom"))))
    db.commit()
    assert stats.llm_failed >= 1
    assert row(db, profiles["Ironji-Trade"], o).score_reason == NO_MODEL_REASON
    score_user(db, uid, deps=deps(FakeScoreLLM(judgement())))
    db.commit()
    assert (
        row(db, profiles["Ironji-Trade"], o).score_breakdown["model"] == "fake-score-1"
    )


def test_llm_cap_per_run(db, profiles, make_opp):
    opps = [
        make_opp(
            f"{COLD} lot {i}",
            tags=["service:cold chain transport"],
            value_amount=9e6,
            value_currency="RWF",
        )
        for i in range(3)
    ]
    ironji = profiles["Ironji-Trade"]
    llm = FakeScoreLLM(judgement())
    stats = backfill_profile(db, ironji.id, deps=deps(llm, max_llm_calls_per_run=1))
    db.commit()
    assert len(llm.calls) == 1 and stats.capped == 2
    models = [row(db, ironji, o).score_breakdown["model"] for o in opps]
    assert models.count("fake-score-1") == 1 and models.count(None) == 2
    # The next run judges the rest and reuses the first.
    llm2 = FakeScoreLLM(judgement())
    stats = backfill_profile(db, ironji.id, deps=deps(llm2, max_llm_calls_per_run=5))
    db.commit()
    assert len(llm2.calls) == 2 and stats.llm_reused == 1


def test_reuse_until_profile_or_opportunity_changes(db, profiles, make_opp):
    o = make_opp(
        COLD,
        tags=["service:cold chain transport"],
        value_amount=9e6,
        value_currency="RWF",
    )
    ironji = profiles["Ironji-Trade"]
    backfill_profile(db, ironji.id, deps=deps(FakeScoreLLM(judgement())))
    db.commit()
    first = row(db, ironji, o)
    first_updated = first.updated_at

    llm = FakeScoreLLM(judgement())
    stats = backfill_profile(db, ironji.id, deps=deps(llm))
    db.commit()
    assert llm.calls == [] and stats.llm_reused == 1 and stats.unchanged == 1
    assert row(db, ironji, o).updated_at == first_updated  # not rewritten

    # A profile edit (new version) means a new judgement.
    p = db.get(Profile, ironji.id)
    p.data = {**p.data, "services": [*p.data["services"], "warehousing"]}
    p.version += 1
    db.commit()
    llm = FakeScoreLLM(judgement(fit=0.6))
    backfill_profile(db, ironji.id, deps=deps(llm))
    db.commit()
    assert len(llm.calls) == 1
    assert row(db, ironji, o).score_breakdown["fit_confidence"] == 0.6

    # Re-extraction of the item, likewise.
    o.evidence = {
        **o.evidence,
        "_extraction": {"at": (now() + timedelta(seconds=1)).isoformat()},
    }
    db.commit()
    llm = FakeScoreLLM(judgement())
    backfill_profile(db, ironji.id, deps=deps(llm), now=now() + timedelta(seconds=2))
    db.commit()
    assert len(llm.calls) == 1

    # A different scoring model, likewise.
    llm = FakeScoreLLM(judgement())
    llm.model = "fake-score-2"
    backfill_profile(db, ironji.id, deps=deps(llm), now=now() + timedelta(seconds=3))
    db.commit()
    assert len(llm.calls) == 1


def test_match_shortlist(db, profiles, make_opp):
    unrelated = make_opp("Supply of office furniture", tags=["sector:furniture"])
    bare = make_opp("Invitation for Bids")  # no tags, no embedding: kept for the model
    llm = FakeScoreLLM(judgement())
    backfill_profile(db, profiles["Ironji-Trade"].id, deps=deps(llm))
    db.commit()
    r = row(db, profiles["Ironji-Trade"], unrelated)
    _check_contract(r)
    assert r.score_breakdown["fit_word"] is None and r.score_breakdown["model"] is None
    assert [c for c in llm.calls if "office furniture" in c["user"]] == []
    assert [c for c in llm.calls if "Invitation for Bids" in c["user"]]
    assert (
        row(db, profiles["Ironji-Trade"], bare).score_breakdown["model"]
        == "fake-score-1"
    )


def test_embedding_similarity_shortlists_and_profile_embedding_is_cached(
    db, profiles, make_opp
):
    emb = BowEmbedder()
    ironji = profiles["Ironji-Trade"]
    # No tag overlap with the services, but the text is close to the profile text.
    [vec] = emb.embed(
        ["Ironji-Trade business services dry freight cold chain last-mile distribution"]
    )
    near = make_opp(
        "Kigali-based supplier sought", tags=["sector:general"], embedding=vec
    )
    far_vec = emb.embed(["wedding catering"])[0]
    far = make_opp(
        "Catering for a wedding", tags=["sector:catering"], embedding=far_vec
    )
    emb.texts.clear()
    llm = FakeScoreLLM(judgement())
    backfill_profile(db, ironji.id, deps=deps(llm, embedder=emb))
    backfill_profile(db, ironji.id, deps=deps(llm, embedder=emb))
    db.commit()
    assert len(emb.texts) == 1  # one profile embedding, cached on (id, version)
    assert row(db, ironji, near).score_breakdown["model"] == "fake-score-1"
    assert row(db, ironji, far).score_breakdown["model"] is None


def test_score_new_opportunities_since(db, owner, profiles, make_opp):
    old = make_opp(COLD + " (old)", tags=["service:cold chain"])
    db.execute(
        sa.text(
            "UPDATE opportunity SET created_at = now() - interval '2 days', updated_at = now() - interval '2 days' WHERE id = :id"
        ),
        {"id": old.id},
    )
    db.commit()
    since = now() - timedelta(minutes=1)
    new = make_opp(COLD + " (new)", tags=["service:cold chain"])
    expired = make_opp(
        COLD + " (expired)", tags=["service:cold chain"], status="expired"
    )
    score_new_opportunities(db, since, deps=deps(FakeScoreLLM(judgement())))
    db.commit()
    ironji = profiles["Ironji-Trade"]
    assert row(db, ironji, old) is None
    assert row(db, ironji, new).score_breakdown["hard_filtered"] is None
    assert (
        row(db, ironji, expired).score_breakdown["hard_filtered"] == "deadline_passed"
    )


def test_backfill_open_only_and_inactive_profile_skipped(db, profiles, make_opp):
    o = make_opp(COLD, tags=["service:cold chain"])
    closed = make_opp(
        COLD + " (expired)", tags=["service:cold chain"], status="expired"
    )
    ironji = profiles["Ironji-Trade"]
    backfill_profile(db, ironji.id, deps=deps())
    db.commit()
    assert row(db, ironji, o) is not None and row(db, ironji, closed) is None
    assert row(db, profiles["AI lab"], o) is None  # only the given profile
    ai = db.get(Profile, profiles["AI lab"].id)
    ai.active = False
    db.commit()
    assert backfill_profile(db, ai.id, deps=deps()).pairs == 0


def test_testing_only_items_not_scored_for_members(db, make_opp, make_source):
    from blackkite.seed.loader import bootstrap

    member = bootstrap(db, "member@example.com").user
    member.role = "member"
    db.commit()
    testing = make_source(status="testing")
    o = make_opp(COLD, source=testing, tags=["service:cold chain"])
    score_user(db, member.id, deps=deps())
    db.commit()
    n = db.scalar(
        sa.select(sa.func.count())
        .select_from(UserOpportunityScore)
        .where(
            UserOpportunityScore.user_id == member.id,
            UserOpportunityScore.opportunity_id == o.id,
        )
    )
    assert n == 0


def test_never_touches_user_opportunity(db, owner, profiles, make_opp, engine):
    from blackkite.db.models import UserOpportunity

    o = make_opp(COLD, tags=["service:cold chain"])
    db.add(
        UserOpportunity(
            user_id=owner.id, opportunity_id=o.id, state="saved", note="mine"
        )
    )
    db.commit()
    statements: list[str] = []

    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", capture)
    try:
        score_user(db, owner.id, deps=deps(FakeScoreLLM(judgement())))
        db.commit()
    finally:
        sa.event.remove(engine, "before_cursor_execute", capture)
    assert not [
        s for s in statements if "user_opportunity " in s or "user_opportunity\n" in s
    ]
    uo = db.scalar(
        sa.select(UserOpportunity).where(UserOpportunity.user_id == owner.id)
    )
    assert (uo.state, uo.note) == ("saved", "mine")
