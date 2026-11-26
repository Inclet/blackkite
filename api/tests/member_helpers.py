"""Fixtures and helpers shared by the M4 member API tests (calendar, private
items, feed filters). Import the fixtures into a test module with
``from tests.member_helpers import *``."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from blackkite.db.models import Profile
from blackkite.routes.member import now_utc
from tests import factories as f
from tests.conftest import make_user, sign_in
from tests.factories import NOW

__all__ = ["ana", "ben", "fit_for", "frozen", "ids", "items", "login"]


@pytest.fixture
def frozen(app):
    app.dependency_overrides[now_utc] = lambda: NOW
    return app


@pytest.fixture
def login(frozen, outbox) -> Iterator[Callable[[str], TestClient]]:
    clients: list[TestClient] = []

    def make(email: str) -> TestClient:
        c = TestClient(frozen, base_url="https://testserver")
        c.__enter__()
        clients.append(c)
        return sign_in(c, outbox, email)

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def ana(db):
    u = make_user(db, "ana@example.com")
    u.name = "Ana Uwase"
    db.commit()
    return u


@pytest.fixture
def ben(db):
    return make_user(db, "ben@example.com")


def items(client: TestClient, **params) -> list[dict]:
    r = client.get("/api/feed", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def ids(client: TestClient, **params) -> list[str]:
    return [i["id"] for i in items(client, **params)]


def fit_for(
    db, user, *opps, word: str | None = "possible", profile: str = "Feed", value=50
):
    """Give each item a fit word for ``user`` on one profile (made if absent)."""
    prof = db.scalar(
        sa.select(Profile).where(Profile.user_id == user.id, Profile.name == profile)
    ) or f.profile(db, user, profile)
    for o in opps:
        f.score(db, user, o, prof, value, fit_word=word)
    return prof
