"""SQLAlchemy engine/session for the app-level users/chats tables.

This is separate from the LangGraph checkpointer's own Postgres connection
in graph.py, but points at the same database (DATABASE_URL) — it just uses
a different Python driver wrapper (SQLAlchemy's psycopg3 dialect) to talk
to it, since the checkpointer manages its own tables directly via psycopg.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _sqlalchemy_url() -> str:
    raw = os.environ["DATABASE_URL"]
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


engine = create_engine(_sqlalchemy_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for every model that's been imported so far.

    Called explicitly from main.py once the api/ routers (and therefore
    app.models) are already imported, rather than importing models from
    here directly — doing it here would create a circular import between
    app.db and app.models, and depending on import order, Base.metadata
    could still be empty at the time create_all runs.
    """
    Base.metadata.create_all(engine)
