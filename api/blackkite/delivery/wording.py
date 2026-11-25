"""Words and full dates for emails (spec 12: the digest uses full dates).

Dates are Kigali calendar dates: "Monday 30 November 2026"; a deadline with a
stated time adds it ("Closes Monday 7 December 2026, 5pm"); a deadline at
midnight or 23:59 is a whole-day deadline and shows no time.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from blackkite.pipeline.dates import KIGALI

NUMBER_WORDS = [
    "no",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]

TRUST_NOTES = {
    "unconfirmed": "not yet confirmed at the source",
    "conflict": "sources disagree on the date",
}


def number_word(n: int, capital: bool = False) -> str:
    w = NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)
    return w[0].upper() + w[1:] if capital else w


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def full_date(d: date) -> str:
    return f"{d:%A} {d.day} {d:%B} {d.year}"


def _time(t: datetime) -> str | None:
    local = t.astimezone(KIGALI)
    if (local.hour, local.minute) in ((0, 0), (23, 59)):
        return None
    hour = local.hour % 12 or 12
    suffix = "am" if local.hour < 12 else "pm"
    return (
        f"{hour}{suffix}" if local.minute == 0 else f"{hour}:{local.minute:02d}{suffix}"
    )


def deadline_line(deadline: datetime) -> str:
    """Like "Closes Monday 30 November 2026", or with its time: "..., 5pm"."""
    text = f"Closes {full_date(deadline.astimezone(KIGALI).date())}"
    t = _time(deadline)
    return f"{text}, {t}" if t else text


def event_line(start: datetime, end: datetime | None) -> str:
    """Like "Tuesday 1 to Wednesday 2 December 2026", one or several days."""
    s = start.astimezone(KIGALI).date()
    e = end.astimezone(KIGALI).date() if end else s
    if e <= s:
        return full_date(s)
    if (s.year, s.month) == (e.year, e.month):
        return f"{s:%A} {s.day} to {full_date(e)}"
    if s.year == e.year:
        return f"{s:%A} {s.day} {s:%B} to {full_date(e)}"
    return f"{full_date(s)} to {full_date(e)}"


def amount(value: Decimal, currency: str | None) -> str:
    whole = value == value.to_integral_value()
    figure = f"{value:,.0f}" if whole else f"{value:,.2f}"
    code = {"RWF": "FRW"}.get(currency or "", currency or "")
    return f"{code} {figure}".strip()


def value_line(
    value_amount: Decimal | None, currency: str | None, note: str | None
) -> str | None:
    """Like "Value: FRW 12,000,000" or "Value: FRW 12,000,000 (lot 2)", or the note
    alone; None when no value is stated."""
    note = (note or "").strip() or None
    if value_amount is not None:
        text = f"Value: {amount(value_amount, currency)}"
        return f"{text} ({note})" if note else text
    return f"Value: {note}" if note else None


def sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def greeting(now: datetime) -> str:
    h = now.astimezone(KIGALI).hour
    return (
        "Good morning" if h < 12 else ("Good afternoon" if h < 18 else "Good evening")
    )
