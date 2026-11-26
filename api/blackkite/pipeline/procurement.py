"""Normalising procurement records (awards, plan items) from their listed text.

Shared by ``pipeline/awards.py`` and ``pipeline/plans.py``; nothing here touches
the database or the network.

* **Entity names**: whitespace collapsed, leading labels ("Procuring entity:")
  and trailing separators dropped; the dedupe key is ``dedupe.org_key``
  (casefolded, punctuation-free, legal suffixes dropped).
* **Amounts**: digits with the source's separators (``Formats``), and a currency
  from the text ("FRW 4,500,000", "USD 12,000.50", "$300") or, when the text
  names none, the currency the source config states for the page. No currency
  anywhere: the amount is kept with currency NULL (and left out of statistics).
  A range or several numbers ("1,000 - 2,000") is refused, never averaged.
* **Dates**: an explicit year only, never guessed: the config's ``date_formats``
  (each must contain a year) or, without them, the pipeline's own parser
  (``pipeline/dates.parse_date``: day first, year required).
* **Fiscal years**: "2026/2027", "2026-27", "FY 2026/27" -> "2026/27" (second
  year must follow the first). Rwanda's fiscal year runs 1 July to 30 June.
* **Quarters**: "Q3", "Quarter 3", "third quarter" -> "Q3", plus a year when the
  text states one ("Q1 2027"). Turned into dates only with the basis the source
  config states (``fiscal``: Q1 = July to September of the fiscal year's first
  year; ``calendar``: Q1 = January to March) and an explicit year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from blackkite.collectors.base import Formats
from blackkite.pipeline.dates import kigali_date, parse_date
from blackkite.pipeline.dedupe import org_key, title_key
from blackkite.pipeline.extract import normalise_currency

QuarterBasis = Literal["fiscal", "calendar"]
MAX_AMOUNT = Decimal(10) ** 18

_WS = re.compile(r"\s+")
_ENTITY_LABEL = re.compile(
    r"^(?:procuring\s+entity|entity|institution|buyer|client|organi[sz]ation)\s*[:\-]\s*",
    re.IGNORECASE,
)
_EDGE = " \t-–—|:;,·•"
_CURRENCY = re.compile(
    r"(?<![A-Za-z])(US\$|USD|RWF|FRW|RFW|Frw|Rwf|RF|EUR|EURO|EUROS|KES|UGX|TZS|GBP)"
    r"(?![A-Za-z])|(\$|€|£)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d.,\s'’]*")


@dataclass
class Problems:
    """What normalising left out, in plain words, kept on the row's ``raw``."""

    items: list[str] = field(default_factory=list)

    def __call__(self, text: str) -> None:
        if text not in self.items:
            self.items.append(text)


def clean_text(text: str | None, limit: int = 2000) -> str | None:
    if text is None:
        return None
    t = _WS.sub(" ", text).strip()
    return t[:limit] or None


def clean_entity(text: str | None) -> str | None:
    t = clean_text(text, 300)
    if t is None:
        return None
    t = _ENTITY_LABEL.sub("", t).strip(_EDGE)
    return t or None


def entity_key(text: str | None) -> str:
    return org_key(text)


def description_key(text: str | None) -> str:
    return title_key(text)


def ref_key(text: str | None) -> str | None:
    """Tender reference as a key: casefolded, no spaces (``N° 001/W/2026`` ->
    ``n°001/w/2026``). None when empty."""
    t = clean_text(text, 200)
    if not t:
        return None
    return re.sub(r"\s+", "", t).casefold()


def clean_ref(text: str | None) -> str | None:
    t = clean_text(text, 200)
    if t is None:
        return None
    t = re.sub(
        r"^(?:tender\s+)?(?:ref(?:erence)?|no|n°)\.?\s*[:#]?\s*",
        "",
        t,
        flags=re.IGNORECASE,
    )
    return t.strip(_EDGE) or None


# --- amounts ----------------------------------------------------------------------


def _currency_in(text: str) -> tuple[str | None, bool]:
    """(ISO code, whether the text named a currency at all)."""
    codes = set()
    for m in _CURRENCY.finditer(text):
        token = m.group(1) or m.group(2)
        code = {"£": "GBP"}.get(token) or normalise_currency(token)
        if code:
            codes.add(code)
    if len(codes) == 1:
        return codes.pop(), True
    return None, bool(codes)


def parse_money(
    text: str | None, fmt: Formats, problems: Problems, what: str = "amount"
) -> tuple[Decimal | None, str | None]:
    """(amount, currency) from a listed amount; (None, None) when it has no
    single number."""
    t = clean_text(text, 200)
    if not t:
        return None, None
    currency, named = _currency_in(t)
    if named and currency is None:
        problems(f"{what}: more than one currency in {t!r}; left out")
        return None, None
    numbers = [n.strip(" .,'’") for n in _NUMBER.findall(t)]
    numbers = [n for n in numbers if any(c.isdigit() for c in n)]
    if len(numbers) != 1:
        problems(f"{what}: {t!r} is not one amount; left out")
        return None, None
    raw = numbers[0]
    for sep in fmt.thousands_separators:
        raw = raw.replace(sep, "")
    raw = raw.replace("'", "").replace("’", "")
    if fmt.decimal_separator != ".":
        if "." in raw:
            problems(f"{what}: {t!r} does not match the configured separators")
            return None, None
        raw = raw.replace(fmt.decimal_separator, ".")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", raw):
        problems(f"{what}: {t!r} does not match the configured separators")
        return None, None
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None, None
    if amount >= MAX_AMOUNT:
        problems(f"{what}: {t!r} is too large; left out")
        return None, None
    if currency is None:
        currency = fmt.currency
        if currency is None:
            problems(f"{what}: no currency stated; kept without one")
    return amount, currency


# --- dates ------------------------------------------------------------------------


def _has_year(fmt: str) -> bool:
    return "%Y" in fmt or "%y" in fmt


def check_date_format(fmt: str) -> str:
    """Pydantic validator body for ``date_formats`` entries."""
    fmt = fmt.strip()
    if not fmt or len(fmt) > 50:
        raise ValueError("date format must be 1-50 characters")
    if not _has_year(fmt):
        raise ValueError(
            f"date format {fmt!r} has no year (%Y); dates are never guessed"
        )
    if any(d in fmt for d in ("%H", "%I", "%M", "%S", "%p", "%z", "%Z", "%f")):
        raise ValueError(f"date format {fmt!r}: only day, month and year are read")
    try:
        datetime(2026, 11, 26, tzinfo=UTC).strftime(fmt)
    except ValueError as e:
        raise ValueError(f"date format {fmt!r} is not valid: {e}") from None
    return fmt


def parse_day(
    text: str | None, fmt: Formats, problems: Problems, what: str = "date"
) -> date | None:
    """A calendar date with an explicit year, or None (with a problem noted)."""
    t = clean_text(text, 100)
    if not t:
        return None
    if fmt.date_formats:
        for f in fmt.date_formats:
            try:
                return datetime.strptime(t, f).replace(tzinfo=UTC).date()
            except ValueError:
                continue
        problems(f"{what}: {t!r} matches none of the date formats; left out")
        return None
    parsed = parse_date(t, "start")
    if parsed.ok and parsed.value is not None:
        return kigali_date(parsed.value)
    if parsed.status == "no_year":
        problems(f"{what}: {t!r} has no year; not guessed")
    else:
        problems(f"{what}: {t!r} is not a date; left out")
    return None


def plausible(
    d: date | None, today: date, *, back_years: int, ahead_years: int
) -> bool:
    if d is None:
        return True
    return (
        today - timedelta(days=366 * back_years)
        <= d
        <= today + timedelta(days=366 * ahead_years)
    )


# --- fiscal years and quarters ------------------------------------------------------

_FY = re.compile(r"(?<!\d)(20\d{2})\s*[/\-–]\s*(20\d{2}|\d{2})(?!\d)")
_QUARTER = re.compile(
    r"\b(?:q\s*([1-4])|quarter\s*([1-4])|([1-4])(?:st|nd|rd|th)\s+quarter"
    r"|(first|second|third|fourth)\s+quarter)\b",
    re.IGNORECASE,
)
_ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def parse_fiscal_year(text: str | None) -> str | None:
    t = clean_text(text, 100)
    if not t:
        return None
    m = _FY.search(t)
    if not m:
        return None
    first = int(m.group(1))
    second = m.group(2)
    second_full = (
        int(second) if len(second) == 4 else (first // 100) * 100 + int(second)
    )
    if second_full != first + 1:
        return None
    return f"{first}/{str(second_full)[2:]}"


def fiscal_start_year(fiscal_year: str) -> int:
    return int(fiscal_year[:4])


def parse_quarter(text: str | None) -> tuple[str | None, int | None]:
    """("Q1".."Q4" or None, a stated calendar year or None)."""
    t = clean_text(text, 100)
    if not t:
        return None, None
    m = _QUARTER.search(t)
    if not m:
        return None, None
    n = m.group(1) or m.group(2) or m.group(3)
    q = int(n) if n else _ORDINAL[m.group(4).lower()]
    rest = t[: m.start()] + " " + t[m.end() :]
    if _FY.search(rest):
        year = None  # a fiscal year in the same cell; handled by the caller
    else:
        years = _YEAR.findall(rest)
        year = int(years[0]) if len(years) == 1 else None
    return f"Q{q}", year


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def quarter_period(
    quarter: str,
    *,
    basis: QuarterBasis | None,
    fiscal_year: str | None,
    calendar_year: int | None,
) -> tuple[date, date] | None:
    """The quarter as dates, or None when the basis or the year is not stated."""
    q = int(quarter[1])
    if basis == "fiscal" and fiscal_year:
        start_year = fiscal_start_year(fiscal_year)
        month = 7 + 3 * (q - 1)
        year = start_year + (month > 12)
        month = (month - 1) % 12 + 1
    elif basis == "calendar" and calendar_year:
        year, month = calendar_year, 1 + 3 * (q - 1)
    else:
        return None
    return date(year, month, 1), _month_end(year, month + 2)


def fiscal_year_of(d: date) -> str:
    first = d.year if d.month >= 7 else d.year - 1
    return f"{first}/{str(first + 1)[2:]}"


def period_label(start: date, end: date) -> str:
    """Plain words for a planned period: "15 Feb 2027", "January to March 2027",
    "October 2026 to March 2027"."""
    if start == end:
        return f"{start.day} {start:%b %Y}"
    if start.year == end.year:
        return f"{start:%B} to {end:%B %Y}"
    return f"{start:%B %Y} to {end:%B %Y}"
