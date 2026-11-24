"""`bk bootstrap` and `bk seed-sources`."""

import re
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from typer.testing import CliRunner

from blackkite.db.models import DigestSetting, Profile, Source, User
from blackkite.seed.loader import bootstrap, load_seed_profiles, seed_sources

FIRST_ADMIN = "owner@example.com"
SPEC = Path(__file__).resolve().parents[2] / "CLAUDE.md"


def spec_71_yaml() -> dict:
    """The YAML block in CLAUDE.md section 7.1, parsed."""
    text = SPEC.read_text("utf-8")
    section = text[text.index("### 7.1"):]
    block = re.search(r"```yaml\n(.*?)```", section, re.S).group(1)
    return yaml.safe_load(block)


@pytest.mark.skipif(not SPEC.exists(), reason="CLAUDE.md not next to api/")
def test_packaged_seed_equals_spec_71():
    assert load_seed_profiles() == spec_71_yaml()


def test_bootstrap_creates_admin_profiles_and_digest(db):
    r = bootstrap(db, FIRST_ADMIN)
    db.commit()
    assert r.created_user
    user = db.scalar(sa.select(User))
    assert (user.email, user.role, user.status) == (FIRST_ADMIN, "admin", "active")

    seed = load_seed_profiles()
    profiles = {p.name: p for p in db.scalars(sa.select(Profile).where(Profile.user_id == user.id))}
    assert set(profiles) == {p["name"] for p in seed["profiles"]}
    for entry in seed["profiles"]:
        p = profiles[entry["name"]]
        assert p.type == entry["type"]
        assert p.data == {k: v for k, v in entry.items() if k not in ("name", "type")}
        assert p.version == 1 and p.active is True

    ironji = profiles["Ironji-Trade"].data
    assert ironji["capacity"]["owned_trucks"] is None and "owned_trucks" in ironji["capacity"]
    assert ironji["capacity"]["tonnage"] is None
    assert ironji["min_contract_rwf"] == 5000000
    ai = profiles["AI lab"].data
    assert ai["provisional"] is True
    assert ai["registrations_held"] is None and ai["min_contract_rwf"] is None
    assert profiles["Personal"].type == "personal"
    assert profiles["Personal"].data["ticket_range_rwf"] is None

    d = db.scalar(sa.select(DigestSetting).where(DigestSetting.user_id == user.id))
    assert (d.channel, d.frequency, d.day, d.address) == ("email", "weekly", "mon", FIRST_ADMIN)


def test_bootstrap_is_idempotent(db):
    bootstrap(db, FIRST_ADMIN)
    db.commit()
    r = bootstrap(db, "  Owner@Example.com ")
    db.commit()
    assert not r.created_user and r.created_profiles == [] and not r.created_digest
    assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(Profile)) == 3
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestSetting)) == 1


def test_bootstrap_requires_email(db):
    with pytest.raises(ValueError):
        bootstrap(db, None)
    with pytest.raises(ValueError):
        bootstrap(db, "  ")


def test_seed_sources_ten_rows_testing_idempotent(db):
    bootstrap(db, FIRST_ADMIN)
    created = seed_sources(db)
    db.commit()
    assert len(created) == 10
    assert seed_sources(db) == []
    db.commit()
    rows = db.scalars(sa.select(Source)).all()
    assert len(rows) == 10
    assert {s.status for s in rows} == {"testing"}
    admin_id = db.scalar(sa.select(User.id))
    assert {s.added_by for s in rows} == {admin_id}
    by_name = {s.name: s for s in rows}
    assert by_name["Umucyo e-procurement"].kind == "original"
    assert "Low request rate" in by_name["Umucyo e-procurement"].access_note
    assert by_name["BNR"].collector_type == "browser_list"
    for name in ("The New Times business section", "KT Press business section"):
        assert by_name[name].streams == ["funding", "investment", "event"]
        assert by_name[name].kind == "news"
    for name in ("Eventbrite Kigali", "10times Kigali"):
        assert by_name[name].streams == ["event"]
        assert "JSON-LD" in by_name[name].access_note


def test_cli_bootstrap_and_seed(db_url, engine, monkeypatch, tmp_path):
    from blackkite import cli
    from blackkite.config import get_settings
    from blackkite.db.session import get_engine, get_sessionmaker

    monkeypatch.chdir(tmp_path)  # no stray .env file
    monkeypatch.setenv("BK_DATABASE_URL", db_url)
    monkeypatch.setenv("BK_FIRST_ADMIN_EMAIL", FIRST_ADMIN)
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()
    try:
        runner = CliRunner()
        r1 = runner.invoke(cli.app, ["bootstrap"])
        r2 = runner.invoke(cli.app, ["bootstrap"])
        r3 = runner.invoke(cli.app, ["seed-sources"])
        assert r1.exit_code == 0, r1.output
        assert "admin: created" in r1.output
        assert "admin: exists" in r2.output and "profiles created: none" in r2.output
        assert "sources created: 10" in r3.output
        monkeypatch.delenv("BK_FIRST_ADMIN_EMAIL")
        get_settings.cache_clear()
        r4 = runner.invoke(cli.app, ["bootstrap"])
        assert r4.exit_code == 1
    finally:
        get_engine().dispose()
        for f in (get_settings, get_engine, get_sessionmaker):
            f.cache_clear()
