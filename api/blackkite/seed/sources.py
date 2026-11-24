"""Seed sources: CLAUDE.md section 4.5, loaded as status `testing`.

Two table rows name two sites each ("The New Times, KT Press business sections";
"Eventbrite Kigali, 10times Kigali"), so they become two sources each: 10 rows.

Collector config stays a placeholder until the M0 access test. `collector_type`
is the first collector the table lists; the full list of candidates is kept in
config["candidate_collectors"]. Home URLs for the news and event sites are the
site roots; the exact section/listing URLs are set at M0. No site was contacted
to build this list.
"""

from typing import Any

SAMPLE_RUN = "Sample run 2026-11-24 (cloud environment): "
SAME_CAVEAT = "Fetch blocked from cloud; test from host."  # "Same access caveat" in 4.5

# Polite default between requests to one host; Umucyo's note asks for a low rate.
DEFAULT_RATE_LIMIT = 5.0
LOW_RATE_LIMIT = 10.0


def _placeholder(*candidates: str) -> dict[str, Any]:
    return {"placeholder": True, "candidate_collectors": list(candidates)}


SEED_SOURCES: list[dict[str, Any]] = [
    {
        "name": "Umucyo e-procurement",
        "home_url": "https://umucyo.gov.rw",
        "publisher": "Rwanda Public Procurement Authority",
        "kind": "original",
        "streams": ["tender"],
        "collector_type": "html_list",
        "config": _placeholder("html_list", "browser_list"),
        "rate_limit": LOW_RATE_LIMIT,
        "access_note": SAMPLE_RUN
        + "Tender notices, procurement plans, awarded contracts with bidder prices. "
        "Fetch blocked from cloud; test from host. Low request rate.",
    },
    {
        "name": "Job in Rwanda, tenders",
        "home_url": "https://jobinrwanda.com/jobs/tender",
        "publisher": "Job in Rwanda",
        "kind": "publisher",
        "streams": ["tender"],
        "collector_type": "html_list",
        "config": _placeholder("html_list", "email_ingest", "search_query"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN + SAME_CAVEAT + " Check for email alerts first.",
    },
    {
        "name": "The New Times jobs & tenders",
        "home_url": "https://jobs.newtimes.co.rw",
        "publisher": "The New Times",
        "kind": "publisher",
        "streams": ["tender"],
        "collector_type": "html_list",
        "config": _placeholder("html_list", "search_query"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN + SAME_CAVEAT,
    },
    {
        "name": "UNGM",
        "home_url": "https://ungm.org",
        "publisher": "United Nations Global Marketplace",
        "kind": "original",
        "streams": ["tender"],
        "collector_type": "html_list",
        "config": _placeholder("html_list", "json_api"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN
        + "Public notice pages with stable IDs; filter by beneficiary country.",
    },
    {
        "name": "BNR",
        "home_url": "https://bnr.rw",
        "publisher": "National Bank of Rwanda",
        "kind": "original",
        "streams": ["investment"],
        "collector_type": "browser_list",
        "config": _placeholder("browser_list", "json_api"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN + "JS front end; documents are PDFs.",
    },
    {
        "name": "RSE",
        "home_url": "https://rse.rw",
        "publisher": "Rwanda Stock Exchange",
        "kind": "original",
        "streams": ["investment"],
        "collector_type": "html_list",
        "config": _placeholder("html_list"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN + "Bond market table was reachable.",
    },
    {
        "name": "The New Times business section",
        "home_url": "https://www.newtimes.co.rw",
        "publisher": "The New Times",
        "kind": "news",
        "streams": ["funding", "investment", "event"],
        "collector_type": "rss",
        "config": _placeholder("rss", "search_query"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": None,  # 4.5 records no access notes for this row
    },
    {
        "name": "KT Press business section",
        "home_url": "https://www.ktpress.rw",
        "publisher": "KT Press",
        "kind": "news",
        "streams": ["funding", "investment", "event"],
        "collector_type": "rss",
        "config": _placeholder("rss", "search_query"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": None,
    },
    {
        "name": "Eventbrite Kigali",
        "home_url": "https://www.eventbrite.com",
        "publisher": "Eventbrite",
        "kind": "publisher",
        "streams": ["event"],
        "collector_type": "html_list",
        "config": _placeholder("html_list"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN + "JSON-LD event data on listing pages.",
    },
    {
        "name": "10times Kigali",
        "home_url": "https://10times.com",
        "publisher": "10times",
        "kind": "publisher",
        "streams": ["event"],
        "collector_type": "html_list",
        "config": _placeholder("html_list"),
        "rate_limit": DEFAULT_RATE_LIMIT,
        "access_note": SAMPLE_RUN + "JSON-LD event data on listing pages.",
    },
]
