from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def database_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "test.sqlite"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = make_engine(f"sqlite:///{database_path}")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(database_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    with factory() as session:
        yield session
