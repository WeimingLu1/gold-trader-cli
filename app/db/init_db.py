"""Database initialization CLI command."""
import typer
from app.db.models import Base
from app.db.session import get_engine

cli = typer.Typer()


@cli.command()
def init_db():
    """Create all database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    typer.echo("[green]Database tables created successfully.[/green]")


if __name__ == "__main__":
    cli()
