"""Normalising procurement records and the rules-based category tagger. No database."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from blackkite.pipeline import categories as C
from blackkite.pipeline import procurement as P

F = P.Formats()


def money(text, fmt=F):
    problems = P.Problems()
    return P.parse_money(text, fmt, problems), problems.items


@pytest.mark.parametrize(
    "text, expected",
    [
        ("FRW 4,500,000", (Decimal("4500000.00"), "RWF")),
        ("4 500 000 Rwf", (Decimal("4500000.00"), "RWF")),
        ("USD 12,000.50", (Decimal("12000.50"), "USD")),
        ("$300", (Decimal("300.00"), "USD")),
        ("RWF 1,234,567.8", (Decimal("1234567.80"), "RWF")),
    ],
)
def test_amounts_with_currency(text, expected):
    assert money(text)[0] == expected


def test_amount_without_currency_uses_the_configured_one_or_none():
    (value, problems) = money("4,500,000")
    assert value == (Decimal("4500000.00"), None)
    assert problems == ["amount: no currency stated; kept without one"]
    assert money("4,500,000", P.Formats(currency="RWF"))[0] == (
        Decimal("4500000.00"),
        "RWF",
    )


@pytest.mark.parametrize(
    "text", ["1,000 - 2,000", "RWF 5,000 or USD 4", "see document", "1,2,3.456"]
)
def test_amounts_refused_not_guessed(text):
    value, problems = money(text)
    assert value == (None, None)
    assert problems


def test_european_separators():
    fmt = P.Formats(decimal_separator=",", thousands_separators=(".", " "))
    assert money("1.234.567,50 FRW", fmt)[0] == (Decimal("1234567.50"), "RWF")


def day(text, fmt=F):
    problems = P.Problems()
    return P.parse_day(text, fmt, problems), problems.items


def test_dates_need_an_explicit_year():
    assert day("30/11/2026")[0] == date(2026, 11, 30)
    assert day("3 Feb 2027")[0] == date(2027, 2, 3)
    assert day("3 Feb") == (None, ["date: '3 Feb' has no year; not guessed"])
    fmt = P.Formats(date_formats=("%Y.%m.%d",))
    assert day("2026.11.30", fmt)[0] == date(2026, 11, 30)
    assert day("30/11/2026", fmt)[0] is None


def test_date_formats_must_hold_a_year():
    assert P.check_date_format("%d/%m/%Y") == "%d/%m/%Y"
    with pytest.raises(ValueError, match="no year"):
        P.check_date_format("%d %b")
    with pytest.raises(ValueError, match="only day, month and year"):
        P.check_date_format("%d/%m/%Y %H:%M")


@pytest.mark.parametrize(
    "text, fy",
    [
        ("2026/2027", "2026/27"),
        ("FY 2026-27", "2026/27"),
        ("2026/27", "2026/27"),
        ("2026/2028", None),
        ("2026", None),
    ],
)
def test_fiscal_years(text, fy):
    assert P.parse_fiscal_year(text) == fy


def test_quarters_to_dates_only_with_basis_and_year():
    assert P.parse_quarter("Q3") == ("Q3", None)
    assert P.parse_quarter("Third quarter 2027") == ("Q3", 2027)
    assert P.parse_quarter("Quarter 1 FY 2026/27") == ("Q1", None)
    assert P.quarter_period(
        "Q3", basis="fiscal", fiscal_year="2026/27", calendar_year=None
    ) == (date(2027, 1, 1), date(2027, 3, 31))
    assert P.quarter_period(
        "Q1", basis="fiscal", fiscal_year="2026/27", calendar_year=None
    ) == (date(2026, 7, 1), date(2026, 9, 30))
    assert P.quarter_period(
        "Q4", basis="calendar", fiscal_year=None, calendar_year=2027
    ) == (date(2027, 10, 1), date(2027, 12, 31))
    assert (
        P.quarter_period("Q3", basis=None, fiscal_year="2026/27", calendar_year=None)
        is None
    )
    assert (
        P.quarter_period(
            "Q3", basis="calendar", fiscal_year="2026/27", calendar_year=None
        )
        is None
    )


def test_entities_and_refs():
    assert P.clean_entity("  Procuring entity: Example  Agency (fictional) - ") == (
        "Example Agency (fictional)"
    )
    assert P.entity_key("Example Agency Ltd") == P.entity_key("example agency")
    assert P.clean_ref("Ref: 001/G/2026") == "001/G/2026"
    assert P.ref_key(" 001 / G / 2026 ") == "001/g/2026"


def test_period_label():
    assert P.period_label(date(2027, 2, 15), date(2027, 2, 15)) == "15 Feb 2027"
    assert P.period_label(date(2027, 1, 1), date(2027, 3, 31)) == (
        "January to March 2027"
    )
    assert P.period_label(date(2026, 10, 1), date(2027, 3, 31)) == (
        "October 2026 to March 2027"
    )


@pytest.mark.parametrize(
    "text, category",
    [
        ("Transport of maize from district stores", "transport"),
        ("Supply and delivery of office furniture", "office"),
        ("Feasibility study for a feeder road", "consultancy"),
        ("Construction of a classroom block", "construction"),
        ("Development of a management information system", "ict"),
        ("Provision of catering services", "food"),
        ("Purchase of assorted items", "other"),
    ],
)
def test_categories(text, category):
    assert C.categorise(text).category == category


def test_category_tags_use_the_extraction_vocabulary():
    got = C.categorise("Cold chain transport and data collection")
    assert got.category == "transport"
    assert got.tags == ["sector:transport", "sector:ict"]
    assert C.label("transport") == "Transport and logistics"
    assert C.label("nope") == "Other"


def test_opportunity_category_prefers_a_matching_sector_tag():
    opp = SimpleNamespace(
        title="Tender notice", subtype=None, summary=None, tags=["sector:ict"]
    )
    assert C.opportunity_category(opp) == "ict"
    opp = SimpleNamespace(
        title="Refrigerated transport of vaccines",
        subtype=None,
        summary=None,
        tags=["sector:health"],
    )
    assert C.opportunity_category(opp) == "transport"
