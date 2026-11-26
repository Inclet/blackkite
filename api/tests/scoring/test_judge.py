"""Checks on the model's judgement before use (no database)."""

from __future__ import annotations

from blackkite.llm.prompt import load_prompt
from blackkite.scoring.judge import UNSUPPORTED_CAP, JudgementReply, check_judgement

NOTICE = (
    "Provision of cold chain transport services\n"
    "Bidders must provide “three refrigerated trucks” for each district.\n"
    "Bids close on 30 December 2026."
)


def reply(**kw) -> JudgementReply:
    base = {
        "fit_confidence": 0.8,
        "eligibility_confidence": 0.7,
        "reason": (
            'It asks that "Bidders must provide "three refrigerated trucks"", which '
            "your network has. Extra."
        ),
        "quote": 'Bidders must provide "three refrigerated trucks"',
        "flags": [],
    }
    return JudgementReply.model_validate({**base, **kw})


def test_supported_quote_keeps_reason_one_sentence():
    j = check_judgement(reply(), NOTICE, "m")
    assert j.reason == (
        'It asks that "Bidders must provide "three refrigerated trucks"", which '
        "your network has."
    )
    assert j.fit_confidence == 0.8 and j.rejected == []


def test_reason_without_the_quote_gets_it_appended():
    j = check_judgement(reply(reason="It is about cold chain transport."), NOTICE, "m")
    assert j.reason.endswith('“Bidders must provide "three refrigerated trucks"”.')


def test_unsupported_quote_rejects_reason_and_caps():
    j = check_judgement(
        reply(quote="ISO 22000 certificate required", fit_confidence=0.99), NOTICE, "m"
    )
    assert j.reason is None and "reason" in j.rejected
    assert (
        j.fit_confidence == UNSUPPORTED_CAP
        and j.eligibility_confidence == UNSUPPORTED_CAP
    )


def test_too_short_quote_is_unsupported():
    assert check_judgement(reply(quote="cold"), NOTICE, "m").reason is None


def test_flags_need_quotes_and_are_capped():
    flags = [
        {
            "kind": "capacity",
            "quote": "three refrigerated trucks",
            "to_check": "Check trucks. More.",
        }
    ] * 4
    flags.append(
        {"kind": "other", "quote": "not in the notice at all", "to_check": "x"}
    )
    j = check_judgement(reply(flags=flags), NOTICE, "m")
    assert len(j.flags) == 3
    assert {(f.code, f.label) for f in j.flags} == {
        ("model_capacity", "Check capacity")
    }
    assert j.flags[0].to_check == "Check trucks."


def test_prompt_is_versioned():
    p = load_prompt("score-v1")
    assert p.version == "score-v1" and "record_judgement" in p.text


def test_profile_prompt_includes_fields_rules_do_not_read_yet():
    from blackkite.db.models import Profile
    from blackkite.scoring.judge import profile_for_prompt

    p = Profile(
        name="Personal",
        type="personal",
        data={
            "streams": ["event"],
            "locations": ["Kigali", "Musanze"],
            "horizon": "3-5 years",
            "availability": "evenings",
            "budget_rwf": 50000,
            "unknown_key": "not sent",
        },
    )
    out = profile_for_prompt(p)
    assert out["locations"] == ["Kigali", "Musanze"]
    assert (out["horizon"], out["availability"], out["budget_rwf"]) == (
        "3-5 years",
        "evenings",
        50000,
    )
    assert "unknown_key" not in out
