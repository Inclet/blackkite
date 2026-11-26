"""`bk` command line."""

from pathlib import Path

import typer

from blackkite.config import get_settings, warn_ignored_env

app = typer.Typer(help="Blackkite command line.", no_args_is_help=True)

API_DIR = Path(__file__).resolve().parent.parent


@app.callback()
def _startup(ctx: typer.Context) -> None:
    # Runs before every command, so any command that sends mail (now or later)
    # warns about an old BK_PUBLIC_BASE_URL that would otherwise go unnoticed.
    # Not for the renderer: it reads no .env file at all (decision 46).
    if ctx.invoked_subcommand != "renderer":
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


@app.command("demo-seed")
def demo_seed_cmd() -> None:
    """Load a small FICTIONAL catalogue into a dev database and score it for the
    bootstrap admin, so you can see a ranked feed and a dry-run digest before
    real sources exist.

    About 10 made-up items across the four streams ("[Demo]" titles, invented
    organisations, example.com links), on two fictional active sources that are
    never collected, plus fictional awards and procurement plan items for the
    benchmarks and "coming up" screens. Scoring is rules-only: no model, no API keys, no network,
    so tenders and funding show at most a "Possible" fit. Re-running replaces
    the demo items with fresh dates.

    Runs only when BK_ENV=dev and the database has no non-demo opportunities.
    Creates the admin from BK_FIRST_ADMIN_EMAIL (like bk bootstrap) if needed.

    This is NOT the Phase 4 exit check: that needs real collected data.

    Then: bk digest --user "$BK_FIRST_ADMIN_EMAIL" --dry-run"""
    from blackkite.db.session import get_sessionmaker
    from blackkite.seed.demo import DemoRefused, demo_seed

    settings = get_settings()
    with get_sessionmaker()() as db:
        try:
            r = demo_seed(db, env=settings.env, admin_email=settings.first_admin_email)
        except DemoRefused as e:
            db.rollback()
            typer.echo(f"refused: {e}", err=True)
            raise typer.Exit(1) from None
        db.commit()
    typer.echo(
        f"demo catalogue: {r.items} fictional items on {r.sources} demo sources"
        + (f" (replaced {r.replaced})" if r.replaced else "")
    )
    typer.echo(f"fictional procurement data: {r.awards} awards, {r.plans} plan items")
    typer.echo(f"scored for the admin, rules only: {r.stats.summary()}")
    typer.echo("not the Phase 4 exit check; that needs real collected data")
    typer.echo('next: bk digest --user "$BK_FIRST_ADMIN_EMAIL" --dry-run')


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


@app.command("digest")
def digest_cmd(
    user: str = typer.Option(..., "--user", help="Email of the account."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the rendered digest; send and log nothing."
    ),
    at: str | None = typer.Option(
        None, hidden=True, help="ISO time to build the digest for (tests)."
    ),
) -> None:
    """Build one user's weekly digest now. With --dry-run, print both parts
    (plain text and HTML) without sending or logging. Without it, send through
    the configured transport (console or Mailpit in dev) and log it; a digest
    already sent today (Kigali) is not sent again.

    Exit codes: 0 sent or printed, 1 no such user, 2 nothing to send."""
    from datetime import UTC, datetime

    from blackkite.auth.service import find_user_by_email
    from blackkite.db.session import get_sessionmaker
    from blackkite.delivery.build import (
        build_digest,
        digest_mail,
        email_setting,
        send_digest,
    )
    from blackkite.delivery.mail import format_console, make_transport

    settings = get_settings()
    now = datetime.fromisoformat(at) if at else datetime.now(UTC)
    with get_sessionmaker()() as db:
        account = find_user_by_email(db, user)
        if account is None:
            typer.echo("error: no account with that email", err=True)
            raise typer.Exit(1)
        if dry_run:
            built = build_digest(db, account, settings, now)
            db.rollback()
            if built.view is None:
                typer.echo("nothing to send: no items and no saved items closing")
                raise typer.Exit(2)
            setting = email_setting(db, account)
            to = setting.address if setting else account.email
            typer.echo(
                format_console(digest_mail(built.view, to, built.headers), "dry run")
            )
            return
        out = send_digest(
            db,
            account,
            settings,
            make_transport(settings),
            now,
            respect_frequency=False,
        )
    if out.status == "empty":
        typer.echo("nothing to send: no items and no saved items closing")
        raise typer.Exit(2)
    if out.status != "sent":
        typer.echo(f"not sent: {out.status.replace('_', ' ')}")
        raise typer.Exit(2)
    typer.echo("digest sent")


@app.command("rotate-unsubscribe")
def rotate_unsubscribe(
    user: str = typer.Option(..., "--user", help="Email of the account."),
) -> None:
    """Revoke every unsubscribe link already sent to one account (decision 43).
    Emails sent from now on carry new links. Exit code 1: no such user."""
    from blackkite.auth.service import find_user_by_email
    from blackkite.db.session import get_sessionmaker
    from blackkite.delivery.unsubscribe import rotate_nonce

    with get_sessionmaker()() as db:
        account = find_user_by_email(db, user)
        if account is None:
            typer.echo("error: no account with that email", err=True)
            raise typer.Exit(1)
        rotate_nonce(account)
        db.commit()
    typer.echo("unsubscribe links revoked; new emails carry new links")


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
    from datetime import UTC, datetime

    import sqlalchemy as sa

    from blackkite.db.models import Profile
    from blackkite.db.session import get_sessionmaker
    from blackkite.scoring.backfill import clear_requests
    from blackkite.scoring.service import score_user

    deps = _scoring_deps()
    with get_sessionmaker()() as db:
        found = _find_user(db, user)
        if found.status != "active":
            typer.echo(f"error: {found.email} is deactivated", err=True)
            raise typer.Exit(1)
        started = datetime.now(UTC)
        pids = list(
            db.scalars(
                sa.select(Profile.id).where(
                    Profile.user_id == found.id, Profile.active.is_(True)
                )
            )
        )
        stats = score_user(db, found.id, deps=deps)
        clear_requests(db, pids, started)  # the worker need not repeat this run
        db.commit()
    _echo_scoring(deps, stats)


@app.command("backfill")
def backfill_cmd(
    profile: str = typer.Option(..., "--profile", help="Profile id."),
) -> None:
    """Match and score one profile over the currently open items (spec 5 backfill)."""
    import uuid
    from datetime import UTC, datetime

    from blackkite.db.models import Profile
    from blackkite.db.session import get_sessionmaker
    from blackkite.scoring.backfill import clear_requests
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
        started = datetime.now(UTC)
        stats = backfill_profile(db, pid, deps=deps)
        clear_requests(db, [pid], started)  # the worker need not repeat this run
        db.commit()
    _echo_scoring(deps, stats)


@app.command()
def worker(
    once: bool = typer.Option(
        False,
        "--once",
        help=(
            "Run exactly one tick, then exit. A profile backfill waits until 60 s "
            "(the backfill debounce) after the last profile edit, so after an edit "
            "run this again a minute later, or add --no-debounce."
        ),
    ),
    no_debounce: bool = typer.Option(
        False,
        "--no-debounce",
        help=(
            "With --once: run pending profile backfills now, without the 60 s "
            "wait after an edit (failed ones still wait for their retry time)."
        ),
    ),
) -> None:
    """Run the scheduler: every active/testing source on its schedule."""
    from blackkite.db.session import get_sessionmaker
    from blackkite.worker.main import main as worker_main

    if no_debounce and not once:
        typer.echo(
            "error: --no-debounce is for manual runs; use it with --once", err=True
        )
        raise typer.Exit(2)
    worker_main(get_settings(), get_sessionmaker(), once=once, debounce=not no_debounce)


@app.command()
def renderer(
    host: str = typer.Option("127.0.0.1", help="Address to listen on."),
    port: int = typer.Option(8100, help="Port to listen on."),
) -> None:
    """Run the renderer service (decision 46): headless Chromium for
    browser_list, holding no secrets. Needs BK_RENDERER_TOKEN; refuses to start
    if a database URL, API key or password is in its environment."""
    from pydantic import ValidationError

    from blackkite.renderer.service import RendererConfigError, create_app

    try:
        application = create_app()
    except RendererConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from None
    except ValidationError as e:
        for err in e.errors():
            where = ".".join(str(x) for x in err["loc"]) or "settings"
            name = f"BK_RENDERER_{where.upper()}" if where != "settings" else where
            msg = err["msg"].removeprefix("Value error, ")
            typer.echo(f"error: {name}: {msg}", err=True)
        raise typer.Exit(2) from None
    import uvicorn

    uvicorn.run(
        application, host=host, port=port, server_header=False, proxy_headers=False
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
