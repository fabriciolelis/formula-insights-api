from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from app.database import MIGRATIONS_DIR


def alembic_config(connection) -> Config:
    """Alembic config that runs over an existing connection, without alembic.ini logging."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), revision)


def stamp(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.stamp(alembic_config(connection), revision)
