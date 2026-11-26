"""link_tender narrows candidates in SQL (pg_trgm, initials index) with the same
links as checking every unlinked record (M5 perf). Fictional names only."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

from blackkite.db import trgm
from blackkite.db.models import Award, Opportunity, ProcurementPlanItem, Source
from blackkite.pipeline import records as R
from blackkite.pipeline.dedupe import _initials, org_key
from blackkite.pipeline.procurement import description_key, entity_key

NOW = datetime(2026, 11, 26, 9, 0, tzinfo=UTC)

ENTITIES = [
    "Rwanda Transport Development Agency (fictional)",
    "RTDA",
    "Example Ministry of Health (fictional)",
    "Example Ministry of Heath (fictional)",  # typo: fuzzy match only
    "Ministère de la Santé Exemple",
    "Example Grain Board Ltd",
    "Another Board (fictional)",
    "",
]
TITLES = [
    "Supply of laptops for district offices",
    "Laptops for district offices, supply of",
    "Transport of grain to regional stores",
    "Construction of a health centre in Huye",
    "Invitation for bids",
    "Supply of office furniture",
    "Cleaning services for head office",
]
TENDERS = [
    (
        "Supply of laptops for district offices",
        "Example Ministry of Health (fictional)",
        None,
    ),
    (
        "Tender for transport of grain to regional stores (lot 2)",
        "Example Grain Board",
        None,
    ),
    (
        "Construction of a health centre in Huye",
        "Rwanda Transport Development Agency (fictional)",
        "RTDA",
    ),
    ("Supply of office furniture", "Ministère de la Santé Exemple", None),
    ("Invitation for bids", "Another Board (fictional)", None),
]


@pytest.fixture
def src(db):
    s = Source(
        name="Records (test)",
        home_url="https://records.example",
        streams=["tender"],
        kind="original",
        collector_type="custom",
        config={},
        status="testing",
    )
    db.add(s)
    db.flush()
    return s


def _records(db, src):
    n = 0
    for e in ENTITIES:
        for t in TITLES:
            n += 1
            ref = f"EX/{n:03d}/2026" if n % 5 == 0 else None
            db.add(
                Award(
                    ref_key=ref.lower() if ref else f"title:{n}",
                    tender_ref=ref,
                    title=t,
                    entity=e or None,
                    entity_key=entity_key(e),
                    first_seen=NOW,
                    last_seen=NOW - timedelta(days=n % 3),
                    source_id=src.id,
                    url="https://records.example/a",
                )
            )
            if e:
                db.add(
                    ProcurementPlanItem(
                        entity=e,
                        entity_key=entity_key(e),
                        description=t,
                        description_key=description_key(t),
                        fiscal_year=f"20{n % 90 + 10}/{n % 90 + 11}",
                        tender_ref=ref,
                        planned_start=date(2027, 1, 1),
                        planned_end=date(2027, 3, 31),
                        source_id=src.id,
                        url="https://records.example/p",
                    )
                )
    db.flush()


def _tenders(db):
    out = []
    for i, (title, org, short) in enumerate(TENDERS):
        o = Opportunity(
            stream="tender",
            title=title,
            organisation=org,
            organisation_short=short,
            evidence={"_sources": {"x": {"title": f"Ref EX/{(i + 1) * 5:03d}/2026"}}},
            visibility="public",
            published_at=NOW - timedelta(days=10),
        )
        db.add(o)
        out.append(o)
    db.flush()
    return out


def _links(db) -> dict:
    out = {}
    for model in (Award, ProcurementPlanItem):
        for r in db.execute(sa.select(model.id, model.opportunity_id)):
            out[(model.__name__, r[0])] = r[1]
    return out


def test_sql_narrowing_links_exactly_as_the_full_scan(db, src, monkeypatch):
    assert trgm.available(db)
    _records(db, src)
    tenders = _tenders(db)

    sp = db.begin_nested()
    monkeypatch.setattr(trgm, "available", lambda s: False)
    full = [R.link_tender(db, o, NOW) for o in tenders]
    full_links = _links(db)
    sp.rollback()
    db.expire_all()
    monkeypatch.undo()

    narrowed = [R.link_tender(db, o, NOW) for o in tenders]
    assert narrowed == full and sum(full) > 5
    assert _links(db) == full_links


def test_candidates_are_narrowed(db, src):
    _records(db, src)
    [laptops] = [o for o in _tenders(db) if o.title.startswith("Supply of laptops")]
    tender = R._tender_of(laptops)
    text = f"{laptops.title} {laptops.evidence}".lower()
    got = R._candidates(db, Award, tender, text, NOW)
    total = db.scalar(sa.select(sa.func.count()).select_from(Award))
    assert 0 < len(got) < total
    # "Another Board" awards with a title far from the tender's never load.
    assert not any(
        a.entity_key == entity_key("Another Board (fictional)")
        and a.title == "Cleaning services for head office"
        and a.tender_ref is None
        for a in got
    )


@pytest.mark.parametrize(
    "name",
    [
        "Rwanda Transport Development Agency",
        "Ministry of the Environment and Natural Resources",
        "Office of the Auditor General",
        "Ministère de la Santé",
        "of",
        "RTDA",
        "City of Kigali",
    ],
)
def test_initials_sql_matches_python(db, name):
    key = org_key(name)
    sql = trgm.initials_sql("k")
    got = db.scalar(
        sa.text(f"SELECT {sql} FROM (SELECT CAST(:k AS text) AS k) t"), {"k": key}
    )
    assert got == _initials(key)


def test_index_expression_is_used(db):
    """The query expression matches the migration's initials index."""
    db.execute(sa.text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(
        r[0]
        for r in db.execute(
            sa.text(
                f"EXPLAIN SELECT id FROM award WHERE "
                f"{trgm.initials_sql('entity_key')} = 'rtda'"
            )
        )
    )
    assert "ix_award_entity_initials" in plan
    plan = "\n".join(
        r[0]
        for r in db.execute(
            sa.text("EXPLAIN SELECT id FROM award WHERE entity_key % 'example board'")
        )
    )
    assert "ix_award_entity_key_trgm" in plan
