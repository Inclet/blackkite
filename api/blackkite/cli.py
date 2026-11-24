"""`bk` command line."""

from pathlib import Path

import typer

from blackkite.config import get_settings

app = typer.Typer(help="Blackkite command line.", no_args_is_help=True)

API_DIR = Path(__file__).resolve().parent.parent


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "db" / "migrations"))
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
    fixture: str = typer.Option("reference", help="Fixture name (see delivery/fixtures)."),
    out: Path = typer.Option(..., help="HTML file to write."),
    logo_src: str = typer.Option("kite.png", help="src of the logo <img> in the page."),
    logo_out: Path | None = typer.Option(None, help="Where to write kite.png (default: beside --out)."),
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
        typer.echo(f"error: unknown fixture {fixture!r}; known: {', '.join(FIXTURES)}", err=True)
        raise typer.Exit(1)
    logo_path = logo_out or out.parent / "kite.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    logo_path.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_digest_preview(FIXTURES[fixture], logo_src=logo_src), "utf-8")
    logo_path.write_bytes(kite_png())
    typer.echo(f"wrote {out} and {logo_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
