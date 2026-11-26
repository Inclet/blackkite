"""Trust copy for the detail pane (desktop) and the phone page (decision C9: the
boards word them differently). Templates follow web/src/fixtures/reference.ts,
filled from the carrying sources' names and the item's dates.

* unconfirmed: "Found on Job in Rwanda, posted 9 Nov. We have not matched it to a
  notice on WFP's own site yet, so check the date there before you act." /
  "Found on Job in Rwanda, posted 9 Nov. Check the date on WFP's own site before
  you act."
* confirmed: "Matched to the call on NCST’s own site." (both layouts); events:
  "Dates and venue match the organiser’s own event page." / "... own page.";
  investments: "Listed on RSE’s own site."
* conflict: "Two sources give different closing dates; the original says 23 Nov."
* added by hand (private, or published by an admin), no source carrying it: the
  owner reads "You added this item yourself, so nobody else has checked it."
  while it is private, and "You added this item and an admin made it public
  with your consent. Nobody has checked it against a source." once published;
  anyone else "A member added this item by hand; check the details with WFP
  before you act." (no organisation: "... check the details before you act.").
  Both layouts use the same sentence.

Apostrophes follow the fixtures: straight in the unconfirmed copy, curly in the
confirmed copy. Wordings not on any board are listed in docs/design-review.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from blackkite.pipeline.dates import kigali_date

# What "the {noun} on X’s own site" calls the original record, per stream.
CONFIRMED_NOUN = {"tender": "notice", "funding": "call"}
NUMBER_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven"]


def short_date(value: datetime) -> str:
    """Short date as the app shows it, for example 9 Nov (Kigali calendar day)."""
    d = kigali_date(value)
    return f"{d.day} {d:%b}"


@dataclass(frozen=True, slots=True)
class LinkInfo:
    """One member-visible source carrying the item."""

    source_name: str
    publisher: str | None
    url: str
    is_original: bool
    first_seen: datetime
    last_seen: datetime

    @property
    def display_name(self) -> str:
        return self.publisher or self.source_name


def trust_copy(
    state: str,
    *,
    stream: str,
    organisation: str | None,
    published_at: datetime | None,
    deadline_at: datetime | None,
    links: list[LinkInfo],
    private: bool,
    manual: bool = False,
    own: bool = False,
) -> tuple[str, str]:
    """(desktop, phone) copy for one trust state. ``manual``: a member added the
    item (private or since published); ``own``: the caller is that member."""
    original = next((link for link in links if link.is_original), None)
    first = min(links, key=lambda link: link.first_seen) if links else None

    if state == "conflict":
        n = len(links)
        count = NUMBER_WORDS[n] if 2 <= n < len(NUMBER_WORDS) else "The"
        text = f"{count} sources give different closing dates"
        if deadline_at is not None:
            if original is not None:
                text += f"; the original says {short_date(deadline_at)}."
            else:
                text += f"; we show the earliest, {short_date(deadline_at)}."
        else:
            text += "."
        return text, text

    if state == "confirmed":
        if stream == "event":
            return (
                "Dates and venue match the organiser’s own event page.",
                "Dates and venue match the organiser’s own page.",
            )
        where = (original or first).display_name if (original or first) else None
        if where is None:
            text = "Confirmed at the source."
        elif stream == "investment":
            text = f"Listed on {where}’s own site."
        else:
            text = f"Matched to the {CONFIRMED_NOUN[stream]} on {where}’s own site."
        return text, text

    if private:
        text = "You added this item yourself, so nobody else has checked it."
        return text, text

    if manual and own and not links:
        text = (
            "You added this item and an admin made it public with your consent. "
            "Nobody has checked it against a source."
        )
        return text, text

    if manual and not links:
        with_org = f" with {organisation}" if organisation else ""
        text = (
            f"A member added this item by hand; check the details{with_org} "
            "before you act."
        )
        return text, text

    issuer = f"{organisation}'s" if organisation else "the issuer's"
    if first is None:
        desktop = (
            f"We have not matched it to a notice on {issuer} own site yet, "
            "so check the date there before you act."
        )
        phone = f"Check the date on {issuer} own site before you act."
        return desktop, phone
    found = f"Found on {first.display_name}"
    if published_at is not None:
        found += f", posted {short_date(published_at)}"
    desktop = (
        f"{found}. We have not matched it to a notice on {issuer} own site yet, "
        "so check the date there before you act."
    )
    phone = f"{found}. Check the date on {issuer} own site before you act."
    return desktop, phone
