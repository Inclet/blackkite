"""`bk` command line."""

from pathlib import Path

import typer

from blackkite.config import get_settings, warn_ignored_env

app = typer.Typer(help="Blackkite command line.", no_args_is_help=True)

API_DIR = Path(__file__).resolve().parent.parent


@app.callback()
def _startup() -> None:
    # Runs before every command, so any command that sends mail (now or later)
    # warns about an old BK_PUBLIC_BASE_URL that would otherwise go unnoticed.
    warn_ignored_env()


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(Path(__file__).parent / "db" / "migrations")
    )
    return cfg


@app.command()
def migrate(revision: str = "head") -> None:
    """Apply database migrations (alembic upgrade)."""
    from alembic import command

    command.upgrade(_alembic_config(), revision)


@app.command()
def bootstrap() -> None:
    """Create the first admin from BK_FIRST_ADMIN_EMAIL with the 7.1 seed profiles. Idempotent."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.seed.loader import bootstrap as do_bootstrap

    settings = get_settings()
    with get_sessionmaker()() as db:
        try:
            r = do_bootstrap(db, settings.first_admin_email)
        except ValueError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(1) from None
        db.commit()
    typer.echo(f"admin: {'created' if r.created_user else 'exists'}")
    typer.echo(f"profiles created: {', '.join(r.created_profiles) or 'none'}")
    typer.echo(f"digest setting: {'created' if r.created_digest else 'exists'}")


@app.command("seed-sources")
def seed_sources() -> None:
    """Load the 4.5 seed sources as status `testing`. Idempotent."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.seed.loader import seed_sources as do_seed

    with get_sessionmaker()() as db:
        created = do_seed(db)
        db.commit()
    typer.echo(f"sources created: {len(created)}")
    for name in created:
        typer.echo(f"  {name}")


@app.command("digest-preview")
def digest_preview(
    fixture: str = typer.Option(
        "reference", help="Fixture name (see delivery/fixtures)."
    ),
    out: Path = typer.Option(..., help="HTML file to write."),
    logo_src: str = typer.Option("kite.png", help="src of the logo <img> in the page."),
    logo_out: Path | None = typer.Option(
        None, help="Where to write kite.png (default: beside --out)."
    ),
) -> None:
    """Write the digest email inside its preview chrome, plus the logo PNG.

    The committed web preview is generated with:
      bk digest-preview --fixture reference --out ../web/public/digest/preview.html
        --logo-src /digest/preview/kite.png --logo-out ../web/public/digest/preview/kite.png
    """
    from blackkite.delivery.digest import render_digest_preview
    from blackkite.delivery.fixtures.digest_reference import FIXTURES
    from blackkite.delivery.logo import kite_png

    if fixture not in FIXTURES:
        typer.echo(
            f"error: unknown fixture {fixture!r}; known: {', '.join(FIXTURES)}",
            err=True,
        )
        raise typer.Exit(1)
    logo_path = logo_out or out.parent / "kite.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    logo_path.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_digest_preview(FIXTURES[fixture], logo_src=logo_src), "utf-8")
    logo_path.write_bytes(kite_png())
    typer.echo(f"wrote {out} and {logo_path}")


# --- sources and worker -------------------------------------------------------------


def _fetch_client(settings, sessions, *, persistent_cache: bool):
    """HTTP client for CLI runs. Tests replace this to inject a fake transport."""
    from blackkite.collectors.http import (
        DbHttpCache,
        MemoryHttpCache,
        make_fetch_client,
    )

    cache = DbHttpCache(sessions) if persistent_cache else MemoryHttpCache()
    return make_fetch_client(settings, cache=cache)


def _find_source(db, ref: str):
    import uuid

    import sqlalchemy as sa

    from blackkite.db.models import Source

    try:
        found = db.get(Source, uuid.UUID(ref))
    except ValueError:
        found = db.scalars(
            sa.select(Source).where(sa.func.lower(Source.name) == ref.lower())
        ).first()
    if found is None:
        typer.echo(f"error: no source {ref!r} (give its name or id)", err=True)
        raise typer.Exit(1)
    return found


@app.command("sources")
def list_sources() -> None:
    """List every source with status, collector, health and last successful run."""
    import sqlalchemy as sa

    from blackkite.db.models import Source
    from blackkite.db.session import get_sessionmaker
    from blackkite.sources.service import source_stats

    with get_sessionmaker()() as db:
        rows = db.scalars(sa.select(Source).order_by(Source.name)).all()
        stats = source_stats(db, [s.id for s in rows])
    if not rows:
        typer.echo("no sources")
        return
    width = max(len(s.name) for s in rows)
    typer.echo(
        f"{'name':<{width}}  {'status':<9} {'collector':<13} {'health':<9} "
        f"{'items 30d':>9}  last success"
    )
    for s in rows:
        st = stats[s.id]
        last = (
            st.last_success_at.strftime("%Y-%m-%d %H:%M UTC")
            if st.last_success_at
            else "never"
        )
        typer.echo(
            f"{s.name:<{width}}  {s.status:<9} {s.collector_type:<13} {st.health:<9} "
            f"{st.items_30d:>9}  {last}"
        )


def _refuse_retired(name: str) -> None:
    typer.echo(f"error: {name} is retired; move it back to testing first", err=True)
    raise typer.Exit(3)


@app.command("run-source")
def run_source_cmd(
    source: str = typer.Argument(..., help="Source name or id."),
) -> None:
    """Run one source now (any status but retired), recording a source_run row.

    Exit codes: 0 ok, 1 run failed or no such source, 2 another worker holds it,
    3 the source is retired (nothing is run or recorded)."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.worker.runner import run_source_locked

    settings = get_settings()
    sessions = get_sessionmaker()
    with sessions() as db:
        found = _find_source(db, source)
        sid, name, status = found.id, found.name, found.status
    if status == "retired":
        _refuse_retired(name)
    client = _fetch_client(settings, sessions, persistent_cache=True)
    try:
        out = run_source_locked(
            sessions, sid, client=client, brave_api_key=settings.brave_api_key
        )
    finally:
        client.close()
    if out.status == "refused_retired":
        _refuse_retired(out.name)
    if out.status == "skipped_locked":
        typer.echo(
            f"{out.name}: another worker is running it; try again later", err=True
        )
        raise typer.Exit(2)
    typer.echo(
        f"{out.name}: {out.status}, found {out.items_found}, new {out.items_new}, "
        f"failed {out.items_failed}"
    )
    if out.error:
        typer.echo(f"error: {out.error}", err=True)
        raise typer.Exit(1)


@app.command("test-source")
def test_source_cmd(
    source: str = typer.Argument(..., help="Source name or id."),
) -> None:
    """Fetch once and print the parsed preview. Writes nothing."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.sources.testrun import preview_source

    settings = get_settings()
    sessions = get_sessionmaker()
    with sessions() as db:
        src = _find_source(db, source)
        db.expunge(src)
    result = preview_source(
        src,
        _fetch_client(settings, sessions, persistent_cache=False),
        brave_api_key=settings.brave_api_key,
    )
    if not result.ok:
        typer.echo(f"{src.name}: test run failed: {result.error}", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"{src.name}: {result.total_parsed} items parsed "
        f"({result.requests_made} requests, {result.elapsed_seconds}s); "
        f"showing {len(result.items)}"
    )
    for i, item in enumerate(result.items, 1):
        typer.echo(f"{i:>2}. {item.title}")
        typer.echo(f"    {item.url}")
        details = [
            f"org: {item.organisation}" if item.organisation else None,
            f"published: {item.listed_published}" if item.listed_published else None,
            f"deadline: {item.listed_deadline}" if item.listed_deadline else None,
        ]
        if line := "; ".join(d for d in details if d):
            typer.echo(f"    {line}")


# --- scoring ---------------------------------------------------------------------------


def _scoring_deps():
    """Scoring clients for CLI runs. Tests replace this to inject fakes."""
    from blackkite.scoring.service import default_deps

    return default_deps()


def _find_user(db, ref: str):
    import uuid

    from blackkite.auth.service import find_user_by_email
    from blackkite.db.models import User

    try:
        found = db.get(User, uuid.UUID(ref))
    except ValueError:
        found = find_user_by_email(db, ref)
    if found is None:
        typer.echo(f"error: no user {ref!r} (give their email or id)", err=True)
        raise typer.Exit(1)
    return found


def _echo_scoring(deps, stats) -> None:
    if deps.llm is None:
        typer.echo(
            "warning: ANTHROPIC_API_KEY is not set; tender and funding pairs were "
            "scored without the model",
            err=True,
        )
    typer.echo(stats.summary())


@app.command("score")
def score_cmd(
    user: str = typer.Option(..., "--user", help="User email or id."),
) -> None:
    """Match and score every active profile of one user over the open items they can see."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.scoring.service import score_user

    deps = _scoring_deps()
    with get_sessionmaker()() as db:
        found = _find_user(db, user)
        if found.status != "active":
            typer.echo(f"error: {found.email} is deactivated", err=True)
            raise typer.Exit(1)
        stats = score_user(db, found.id, deps=deps)
        db.commit()
    _echo_scoring(deps, stats)


@app.command("backfill")
def backfill_cmd(
    profile: str = typer.Option(..., "--profile", help="Profile id."),
) -> None:
    """Match and score one profile over the currently open items (spec 5 backfill)."""
    import uuid

    from blackkite.db.models import Profile
    from blackkite.db.session import get_sessionmaker
    from blackkite.scoring.service import backfill_profile

    try:
        pid = uuid.UUID(profile)
    except ValueError:
        typer.echo(f"error: {profile!r} is not a profile id", err=True)
        raise typer.Exit(1) from None
    deps = _scoring_deps()
    with get_sessionmaker()() as db:
        found = db.get(Profile, pid)
        if found is None:
            typer.echo(f"error: no profile {profile}", err=True)
            raise typer.Exit(1)
        if not found.active:
            typer.echo(f"error: profile {found.name!r} is not active", err=True)
            raise typer.Exit(1)
        stats = backfill_profile(db, pid, deps=deps)
        db.commit()
    _echo_scoring(deps, stats)


@app.command()
def worker() -> None:
    """Run the scheduler: every active/testing source on its schedule."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.worker.main import main as worker_main

    worker_main(get_settings(), get_sessionmaker())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
