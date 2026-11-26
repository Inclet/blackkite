"""Benchmark categories for awards, procurement plans and tenders (spec 8
"Benchmarks: awarded tender prices by category").

Rules only, no model call: a category is chosen from keywords in a title or
description. Tags use the extraction tag vocabulary (``sector:<label>``, see
``pipeline/extract.py``), so an award, a plan and an extracted tender share the
same tag space and the profile matcher reads them the same way.

``categorise(text)`` returns every category whose keywords occur (as whole
words or phrases, case-insensitive) and the primary one: the category with the
most keyword hits, ties broken by the order of ``CATEGORIES``. Text with no hit
is ``other``.

``opportunity_category(opp)`` is the category of a catalogue tender: a
``sector:<key>`` tag that is a category key wins; else the keywords of its
title, subtype, summary and tag labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

OTHER = "other"
OTHER_LABEL = "Other"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    keywords: tuple[str, ...]


# Order breaks ties ("feasibility study for a road": consultancy). "delivery" is
# not a transport keyword: "supply and delivery of ..." is how goods tenders read.
CATEGORIES: tuple[Category, ...] = (
    Category(
        "consultancy",
        "Consultancy and studies",
        (
            "consultancy",
            "consulting",
            "consultant",
            "consultants",
            "feasibility",
            "study",
            "studies",
            "audit",
            "evaluation",
            "assessment",
            "supervision",
            "technical assistance",
            "advisory",
        ),
    ),
    Category(
        "transport",
        "Transport and logistics",
        (
            "transport",
            "transportation",
            "logistics",
            "freight",
            "haulage",
            "trucking",
            "trucks",
            "truck",
            "cargo",
            "courier",
            "distribution",
            "cold chain",
            "refrigerated",
            "vehicle hire",
            "hire of vehicles",
            "removal",
            "clearing and forwarding",
        ),
    ),
    Category(
        "construction",
        "Construction and works",
        (
            "construction",
            "rehabilitation",
            "renovation",
            "civil works",
            "works",
            "building",
            "buildings",
            "road",
            "roads",
            "bridge",
            "plumbing",
            "painting",
        ),
    ),
    Category(
        "ict",
        "IT, software and data",
        (
            "software",
            "ict",
            "it equipment",
            "computer",
            "computers",
            "laptops",
            "laptop",
            "servers",
            "network",
            "networking",
            "website",
            "information system",
            "management system",
            "digital",
            "data",
            "artificial intelligence",
            "cctv",
        ),
    ),
    Category(
        "office",
        "Office supplies, furniture and printing",
        (
            "stationery",
            "office supplies",
            "office furniture",
            "furniture",
            "printing",
            "toner",
            "toners",
            "paper",
        ),
    ),
    Category(
        "food",
        "Food and catering",
        (
            "food",
            "foodstuff",
            "foodstuffs",
            "catering",
            "meals",
            "refreshments",
            "beverages",
        ),
    ),
    Category(
        "cleaning_security",
        "Cleaning and security",
        (
            "cleaning",
            "hygiene",
            "sanitation",
            "fumigation",
            "security",
            "guarding",
        ),
    ),
    Category(
        "medical",
        "Medical and laboratory",
        (
            "medical",
            "medicines",
            "pharmaceutical",
            "pharmaceuticals",
            "drugs",
            "laboratory",
            "reagents",
            "hospital",
        ),
    ),
    Category(
        "agriculture",
        "Agriculture",
        (
            "seeds",
            "fertiliser",
            "fertilizer",
            "fertilizers",
            "agricultural",
            "livestock",
            "irrigation",
            "crops",
            "farming",
        ),
    ),
    Category(
        "energy",
        "Energy, electrical and fuel",
        (
            "electrical",
            "electricity",
            "solar",
            "generator",
            "generators",
            "energy",
            "fuel",
            "lubricants",
        ),
    ),
    Category(
        "vehicles",
        "Vehicles and spare parts",
        (
            "supply of vehicles",
            "acquisition of vehicles",
            "motorcycles",
            "spare parts",
            "tyres",
            "tires",
            "vehicle maintenance",
            "garage",
        ),
    ),
)
BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
KEYS = (*BY_KEY, OTHER)

_PATTERNS = {
    c.key: [
        re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])")
        for k in c.keywords
    ]
    for c in CATEGORIES
}


def label(key: str) -> str:
    c = BY_KEY.get(key)
    return c.label if c else OTHER_LABEL


def tag(key: str) -> str:
    return f"sector:{key}"


@dataclass(frozen=True)
class Categorised:
    category: str
    tags: list[str]


def categorise(*texts: str | None) -> Categorised:
    text = " ".join(t for t in texts if t).lower()
    hits: list[tuple[int, int, str]] = []
    for i, c in enumerate(CATEGORIES):
        n = sum(1 for p in _PATTERNS[c.key] if p.search(text))
        if n:
            hits.append((-n, i, c.key))
    if not hits:
        return Categorised(OTHER, [])
    hits.sort()
    keys = [k for _, _, k in sorted(hits, key=lambda h: h[1])]
    return Categorised(hits[0][2], [tag(k) for k in keys])


def opportunity_category(opp: Any) -> str:
    tags = list(getattr(opp, "tags", None) or [])
    for t in tags:
        if t.startswith("sector:") and t.split(":", 1)[1] in BY_KEY:
            return t.split(":", 1)[1]
    labels = [t.split(":", 1)[-1] for t in tags]
    return categorise(
        opp.title, getattr(opp, "subtype", None), getattr(opp, "summary", None), *labels
    ).category
