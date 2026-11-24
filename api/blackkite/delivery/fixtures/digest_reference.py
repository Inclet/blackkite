"""The weekly digest exactly as design/reference/digest-email.html shows it.

Word for word, including the board's "#" links, which are accepted only inside
allow_placeholder_links(); a real digest must carry http(s) links. First name
only ("Clet", as on the board); no email address belongs in fixtures.
"""

from datetime import date

from blackkite.delivery.digest import (
    DigestFooter,
    DigestItem,
    DigestView,
    allow_placeholder_links,
)

with allow_placeholder_links():
    REFERENCE = DigestView(
        subject="Six things this week, one closing Monday",
        sender="Blackkite",
        first_name="Clet",
        issue_date=date(2026, 11, 23),
        greeting="Good morning",
        intro="Six things made your list this week. Here are the four to look at first.",
        items=[
            DigestItem(
                stream="tender",
                profile_label="Ironji-Trade",
                title="Logistics, transport and warehousing support",
                url="#",
                summary="World Food Programme. It asks for transport and warehousing, which you offer.",
                date_line="Closes Mon 30 Nov",
                trust_note="not yet confirmed at the source",
            ),
            DigestItem(
                stream="event",
                title="ABH Summit and Grand Finale",
                url="#",
                summary="Kigali Convention Centre. Free to attend, seats are first come, first served.",
                date_line="Tue 1 to Wed 2 Dec",
            ),
            DigestItem(
                stream="funding",
                title="Transition to Scale research and innovation call",
                url="#",
                summary=(
                    "National Council for Science and Technology. "
                    "Eligibility for private companies is unclear."
                ),
                date_line="Closes Mon 7 Dec, 5pm",
            ),
            DigestItem(
                stream="funding",
                profile_label="Ironji-Trade",
                title="develoPPP Ventures, cohort 6",
                url="#",
                summary="Up to €100,000, and you need to bring matching funds.",
                date_line="Closes Thu 31 Dec",
            ),
        ],
        cta_url="#",
        more_count=2,
        footer=DigestFooter(
            source_count=8,
            frequency="every Monday",
            change_frequency_url="#",
            unsubscribe_url="#",
        ),
    )

FIXTURES = {"reference": REFERENCE}
