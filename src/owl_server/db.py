"""Database engine, sessions and migrations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_url(url: str) -> str:
    """``postgresql://`` -> the psycopg 3 driver; plain paths -> SQLite (tests, tiny setups)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if "://" not in url:
        return f"sqlite:///{Path(url).expanduser().resolve()}"
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def alembic_config(url: str):  # type: ignore[no-untyped-def]
    """Alembic configuration built in code, so it works from an installed package (no ini file)."""
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", normalize_url(url).replace("%", "%%"))
    return cfg


def upgrade(url: str) -> None:
    from alembic import command

    command.upgrade(alembic_config(url), "head")


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        try:
            return conn.execute(
                text("select version_num from alembic_version")
            ).scalar_one_or_none()
        except Exception:  # noqa: BLE001 - table missing: not migrated
            return None


def head_revision(url: str) -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config(url)).get_current_head() or ""
