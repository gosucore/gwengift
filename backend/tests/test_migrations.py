from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "users",
    "collections",
    "rounds",
    "virtual_gifts",
    "pool_versions",
    "market_snapshots",
    "bets",
    "ledger_entries",
    "drand_proofs",
    "disclosures",
    "draw_leases",
}


def migration_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def test_upgrade_and_downgrade_empty_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.sqlite"
    config = migration_config(database_path)

    command.upgrade(config, "head")
    database_url = config.get_main_option("sqlalchemy.url")
    assert database_url is not None
    engine = create_engine(database_url)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert EXPECTED_TABLES <= tables

        triggers: list[str] = list(
            connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))
            .scalars()
            .all()
        )
        assert len(set(triggers)) == 9
        assert "prevent_bets_binding_update" in triggers

    command.downgrade(config, "base")
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}


def test_engine_creates_missing_sqlite_parent_directory(tmp_path: Path) -> None:
    database_path = tmp_path / "missing" / "nested" / "application.sqlite"
    engine = make_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert database_path.is_file()
    finally:
        engine.dispose()
