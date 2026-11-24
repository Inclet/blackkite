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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
