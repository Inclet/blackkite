"""Schema invariants: per-user tables, constraints, pgvector column."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from blackkite.config import EMBEDDING_DIM
from blackkite.db.models import (
    PER_USER_TABLES,
    Opportunity,
    Profile,
    Source,
    UserOpportunity,
)
from tests.conftest import make_user


def test_every_per_user_table_has_non_null_indexed_user_id(engine):
    insp = sa.inspect(engine)
    for table in PER_USER_TABLES:
        cols = {c["name"]: c for c in insp.get_columns(table)}
        assert "user_id" in cols, table
        assert cols["user_id"]["nullable"] is False, table
        leading = [ix["column_names"][0] for ix in insp.get_indexes(table)]
        assert "user_id" in leading, f"{table}: no index starting with user_id"
        fks = [fk for fk in insp.get_foreign_keys(table) if fk["constrained_columns"] == ["user_id"]]
        assert fks and fks[0]["referred_table"] == "user", table


def test_every_table_with_a_user_id_is_listed_as_per_user(engine):
    insp = sa.inspect(engine)
    with_user_id = {
        t for t in insp.get_table_names()
        if any(c["name"] == "user_id" for c in insp.get_columns(t))
    }
    # login_token.user_id is nullable on purpose: invite holders have no user yet.
    assert with_user_id - {"login_token"} == set(PER_USER_TABLES)


def test_embedding_is_pgvector_with_configured_dimension(engine):
    with engine.connect() as c:
        typ = c.scalar(sa.text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'opportunity'::regclass AND attname = 'embedding'"
        ))
    assert typ == f"vector({EMBEDDING_DIM})"


def test_organisation_short_is_nullable(engine):
    cols = {c["name"]: c for c in sa.inspect(engine).get_columns("opportunity")}
    assert cols["organisation_short"]["nullable"] is True


def test_user_opportunity_unique_per_user_opportunity_profile(engine):
    uniques = sa.inspect(engine).get_unique_constraints("user_opportunity")
    assert any(u["column_names"] == ["user_id", "opportunity_id", "profile_id"] for u in uniques)


def _source(**kw):
    base = dict(name=f"s-{uuid.uuid4().hex[:6]}", home_url="https://example.com",
                streams=["tender"], kind="original", collector_type="rss")
    return Source(**(base | kw))


@pytest.mark.parametrize("sql", [
    "UPDATE source SET status = 'live'",
    "UPDATE source SET kind = 'blog'",
    "UPDATE source SET collector_type = 'ftp'",
    "UPDATE source SET streams = ARRAY['jobs']::varchar[]",
    "UPDATE source SET streams = ARRAY[]::varchar[]",
])
def test_source_enumerations_are_enforced(db, sql):
    db.add(_source())
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(sa.text(sql))
        db.flush()
    db.rollback()


@pytest.mark.parametrize("column,value", [
    ("status", "closed"), ("verification", "confirmed"), ("visibility", "team"), ("stream", "job"),
])
def test_opportunity_enumerations_are_enforced(db, column, value):
    db.add(Opportunity(stream="tender", title="t"))
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(sa.text(f"UPDATE opportunity SET {column} = :v"), {"v": value})
        db.flush()
    db.rollback()


def test_private_opportunity_needs_owner(db):
    db.add(Opportunity(stream="tender", title="t", visibility="private"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_user_opportunity_profile_must_belong_to_same_user(db):
    alice = make_user(db, "alice@example.com")
    bob = make_user(db, "bob@example.com")
    p = Profile(user_id=bob.id, name="p", type="business")
    o = Opportunity(stream="tender", title="t")
    db.add_all([p, o])
    db.commit()
    db.add(UserOpportunity(user_id=alice.id, opportunity_id=o.id, profile_id=p.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_user_email_unique_case_insensitive(db):
    make_user(db, "Case@example.com")
    with pytest.raises(IntegrityError):
        make_user(db, "case@example.com")
    db.rollback()
