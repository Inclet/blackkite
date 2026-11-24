"""Test fixtures. Tests run against a real PostgreSQL 16 with pgvector.

Database: if BK_TEST_DATABASE_URL is set (an SQLAlchemy URL to a server where the
user may CREATE DATABASE, e.g. the compose `db` service), tests use that server.
Otherwise a throwaway cluster is started from the local PostgreSQL 16 binaries
(see tests/pgcluster.py) and removed afterwards.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from blackkite.app import create_app
from blackkite.config import Settings
from blackkite.db.base import Base
from blackkite.db.models import User
from blackkite.db.session import get_db
from blackkite.delivery.mail import MemoryTransport, get_mail_transport
from tests.pgcluster import ThrowawayCluster

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def pg_server_url() -> Iterator[str]:
    """URL of a maintenance database on a server we may create databases on."""
    url = os.environ.get("BK_TEST_DATABASE_URL")
    if url:
        yield url
        return
    cluster = ThrowawayCluster().start()
    try:
        yield cluster.url()
    finally:
        cluster.stop()


@pytest.fixture(scope="session")
def make_database(pg_server_url: str):
    """Factory: create an empty database, return its URL. Dropped at session end."""
    created: list[str] = []
    admin = sa.create_engine(pg_server_url, isolation_level="AUTOCOMMIT")

    def make(prefix: str = "bk_test") -> str:
        name = f"{prefix}_{uuid.uuid4().hex[:8]}"
        with admin.connect() as c:
            c.execute(sa.text(f'CREATE DATABASE "{name}"'))
        created.append(name)
        return make_url(pg_server_url).set(database=name).render_as_string(hide_password=False)

    yield make
    with admin.connect() as c:
        for name in created:
            c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def db_url(make_database) -> str:
    url = make_database("bk_app")
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture(scope="session")
def engine(db_url: str) -> Iterator[sa.Engine]:
    eng = sa.create_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(request) -> Iterator[None]:
    yield
    if "engine" not in request.fixturenames:
        return
    eng: sa.Engine = request.getfixturevalue("engine")
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with eng.begin() as c:
        c.execute(sa.text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def Sessions(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(Sessions) -> Iterator[Session]:
    with Sessions() as s:
        yield s


@pytest.fixture
def settings(db_url: str) -> Settings:
    return Settings(
        database_url=db_url,
        public_base_url="https://testserver",
        cookie_secure=True,
        mail_transport="console",
        _env_file=None,
    )


@pytest.fixture
def outbox() -> MemoryTransport:
    return MemoryTransport()


@pytest.fixture
def app(settings, Sessions, outbox):
    application = create_app(settings)

    def _db():
        with Sessions() as s:
            yield s

    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[get_mail_transport] = lambda: outbox
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, base_url="https://testserver") as c:
        yield c


# --- helpers ----------------------------------------------------------------------

LINK_RE = re.compile(r"https://testserver/auth/verify\?token=\S+")


def token_from_mail(text: str) -> str:
    m = LINK_RE.search(text)
    assert m, f"no sign-in link in mail:\n{text}"
    return parse_qs(urlparse(m.group(0)).query)["token"][0]


def make_user(db: Session, email: str, role: str = "member", status: str = "active") -> User:
    u = User(email=email, role=role, status=status)
    db.add(u)
    db.commit()
    return u


def sign_in(client: TestClient, outbox: MemoryTransport, email: str) -> TestClient:
    """Request a link for `email`, follow it, leave the session cookie on `client`."""
    n = len(outbox.outbox)
    r = client.post("/auth/request-link", json={"email": email})
    assert r.status_code == 202, r.text
    assert len(outbox.outbox) == n + 1, "no mail sent"
    token = token_from_mail(outbox.outbox[-1].text)
    r = client.get("/auth/verify", params={"token": token}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return client
