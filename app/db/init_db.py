"""Database initialization CLI command."""
import typer
from app.db.models import Base as db_base
from app.backtest.models import Base as bt_base
from app.db.session import get_engine

cli = typer.Typer()


@cli.command()
def init_db():
    """Create all database tables (app + backtest)."""
    engine = get_engine()
    db_base.metadata.create_all(engine)
    bt_base.metadata.create_all(engine)
    typer.echo("[green]Database tables created successfully.[/green]")


if __name__ == "__main__":
    cli()
