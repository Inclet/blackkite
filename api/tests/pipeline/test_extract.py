"""Extraction checks: every kept field is backed by a snippet found in the text."""

from decimal import Decimal

import pytest

from blackkite.llm.client import LLMError
from blackkite.pipeline.extract import (
    PROMPT_VERSION,
    ExtractionReply,
    check_reply,
    embedding_text,
    extract,
    recommendation_language,
)
from tests.pipeline.fakes import FakeLLM, q

NOTICE = """Invitation for Bids
Example Districts Agency (EDA)
Supply of refrigerated  transport services for vaccines, Lot 2.
Estimated budget: FRW 25,000,000.
Bids close on 30 November 2026 at 10:00 am.
Bidders must hold a valid “tax clearance certificate”.
Submission through the e-procurement system."""


def full_reply(**over):
    reply = {
        "stream": q("tender", "Invitation for Bids"),
        "subtype": q("rfb", "Invitation for Bids"),
        "title": q(
            "Supply of refrigerated transport services for vaccines, Lot 2",
            "Supply of refrigerated transport services for vaccines, Lot 2.",
        ),
        "organisation": q("Example Districts Agency", "Example Districts Agency (EDA)"),
        "organisation_short": q("EDA", "(EDA)"),
        "summary": q(
            "EDA seeks a carrier for chilled vaccine transport. Bids are due by end of November.",
            "Supply of refrigerated transport services for vaccines",
        ),
        "deadline_at": q(
            "2026-11-30T10:00", "Bids close on 30 November 2026 at 10:00 am."
        ),
        "value_amount": {
            "value": 25000000,
            "snippet": "Estimated budget: FRW 25,000,000.",
        },
        "value_currency": q("FRW", "FRW 25,000,000"),
        "submission_method": q(
            "e-procurement system", "through the e-procurement system"
        ),
        # Curly quotes in the text, straight quotes in the snippet: still a match.
        "requirements": [
            {
                "text": "Tax clearance certificate",
                "snippet": 'valid "tax clearance certificate"',
            }
        ],
        "tags": [
            {
                "tag": "Cold chain transport",
                "kind": "service_type",
                "snippet": "refrigerated transport",
            },
            {"tag": "health", "kind": "sector", "snippet": "vaccines"},
            {"tag": "drones", "kind": "capability", "snippet": "drone delivery"},
        ],
    }
    reply.update(over)
    return ExtractionReply.model_validate(reply)


def test_supported_fields_are_kept_with_their_snippets():
    out = check_reply(full_reply(), NOTICE, ["tender"])
    v = out.values
    assert v["stream"] == "tender"
    assert v["organisation_short"] == "EDA"
    assert v["value_amount"] == Decimal("25000000.00")
    assert v["value_currency"] == "RWF"  # FRW is not ISO 4217
    assert v["deadline_at"] == "2026-11-30T10:00"
    assert v["requirements"] == ["Tax clearance certificate"]
    assert v["tags"] == ["service:cold chain transport", "sector:health"]
    assert out.evidence["deadline_at"]["snippet"].startswith("Bids close")
    assert (
        out.evidence["value_amount"]["snippet"] == "Estimated budget: FRW 25,000,000."
    )
    # Whitespace differences ("refrigerated  transport") do not break a match.
    assert "title" in v
    assert out.dropped == ["tags[]"]  # the drone tag is not in the text


def test_fields_with_invented_snippets_are_stripped():
    reply = full_reply(
        organisation=q("Ministry of Somewhere", "Ministry of Somewhere"),
        value_amount={"value": 99000000, "snippet": "Budget FRW 99,000,000"},
        deadline_at=q("2026-12-15", "Closing date 15 December 2026"),
        fees=q("FRW 20,000", None),
    )
    out = check_reply(reply, NOTICE, ["tender"])
    for name in ("organisation", "value_amount", "deadline_at"):
        assert name not in out.values, name
        assert name in out.dropped
    assert "fees" not in out.values  # no snippet at all
    assert any("snippet is not in the source text" in r for r in out.reasons)


def test_amount_snippet_must_contain_digits():
    reply = full_reply(value_amount={"value": 5, "snippet": "Estimated budget"})
    assert "value_amount" not in check_reply(reply, NOTICE, ["tender"]).values


def test_stream_must_be_one_the_source_feeds():
    out = check_reply(full_reply(), NOTICE, ["funding"])
    assert "stream" not in out.values
    assert any("not one this source feeds" in r for r in out.reasons)


def test_summary_is_cut_to_two_sentences_and_must_not_copy_the_source():
    long = full_reply(summary=q("One. Two. Three.", "Lot 2."))
    assert check_reply(long, NOTICE, ["tender"]).values["summary"] == "One. Two."
    copied = full_reply(
        summary=q(
            "Supply of refrigerated transport services for vaccines, Lot 2.",
            "Lot 2.",
        )
    )
    out = check_reply(copied, NOTICE, ["tender"])
    assert "summary" not in out.values
    assert any("verbatim" in r for r in out.reasons)


BOND = """Treasury Bond Issue
The Central Bank announces a 5-year Treasury bond, coupon 12.5%.
Minimum subscription FRW 100,000. Auction on 9 December 2026."""


@pytest.mark.parametrize(
    "summary",
    [
        "A 5-year bond at 12.5%. Investors should buy before the auction.",
        "A 5-year bond paying 12.5%. This is an attractive investment for savers.",
        "We recommend this five-year bond. Auction in December.",
        "Five-year bond. Don't miss the 12.5% coupon.",
    ],
)
def test_investment_summary_with_recommendation_language_is_removed(summary):
    reply = ExtractionReply.model_validate(
        {
            "stream": q("investment", "Treasury Bond Issue"),
            "summary": q(summary, "a 5-year Treasury bond, coupon 12.5%"),
        }
    )
    out = check_reply(reply, BOND, ["investment"])
    assert "summary" not in out.values
    assert any("recommendation language" in r for r in out.reasons)


def test_factual_investment_summary_is_kept():
    s = "The central bank is issuing a five-year treasury bond with a 12.5% coupon. The minimum to buy is FRW 100,000."
    assert recommendation_language(s) is None
    reply = ExtractionReply.model_validate(
        {
            "stream": q("investment", "Treasury Bond Issue"),
            "summary": q(s, "Minimum subscription FRW 100,000."),
        }
    )
    assert check_reply(reply, BOND, ["investment"]).values["summary"] == s


ADVICE = "A 5-year bond at 12.5%. Investors should buy before the auction."
MULTI = ["funding", "investment", "event"]


def test_multi_stream_source_unknown_stream_is_policed():
    reply = ExtractionReply.model_validate(
        {"summary": q(ADVICE, "a 5-year Treasury bond, coupon 12.5%")}
    )
    out = check_reply(reply, BOND, MULTI)
    assert "summary" not in out.values
    assert any("recommendation language" in r for r in out.reasons)


def test_multi_stream_source_investment_stream_is_policed():
    reply = ExtractionReply.model_validate(
        {
            "stream": q("investment", "Treasury Bond Issue"),
            "summary": q(ADVICE, "a 5-year Treasury bond, coupon 12.5%"),
            "value_note": q(
                "Don't miss the 12.5% coupon", "a 5-year Treasury bond, coupon 12.5%"
            ),
        }
    )
    out = check_reply(reply, BOND, MULTI)
    assert "summary" not in out.values and "value_note" not in out.values


def test_multi_stream_source_other_stream_is_not_policed():
    reply = ExtractionReply.model_validate(
        {
            "stream": q("event", "Treasury Bond Issue"),
            "summary": q(ADVICE, "a 5-year Treasury bond, coupon 12.5%"),
        }
    )
    assert "summary" in check_reply(reply, BOND, MULTI).values


def test_same_phrase_outside_investment_is_not_policed():
    reply = full_reply(
        summary=q("A good opportunity for carriers. Bids due 30 Nov.", "Lot 2.")
    )
    assert "summary" in check_reply(reply, NOTICE, ["tender"]).values


def test_extract_calls_the_model_with_the_versioned_prompt():
    llm = FakeLLM(full_reply())
    out = extract(
        llm, NOTICE, source_name="Example", source_kind="original", streams=["tender"]
    )
    assert out.model == "fake-extract-1" and out.prompt_version == PROMPT_VERSION
    assert "<source_text>" in llm.calls[0]["user"]
    assert "record_opportunity" in llm.calls[0]["system"]


def test_extract_propagates_llm_errors():
    with pytest.raises(LLMError):
        extract(
            FakeLLM(error=LLMError("down")),
            NOTICE,
            source_name="x",
            source_kind="news",
            streams=["tender"],
        )


def test_embedding_text():
    assert embedding_text("T", "S.", ["sector:a"]) == "T\nS.\nTags: sector:a"
