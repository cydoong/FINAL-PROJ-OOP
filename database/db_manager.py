"""
PayrollPro (Python Edition) — Database Manager
=================================================
Owns the SQLAlchemy Engine + Session factory. Because the whole app
is designed to run against *either* backend interchangeably:

    SQLite   -> zero-config, a single .db file (great for a fresh
                install, demos, or running without XAMPP at all)
    MySQL    -> point it at your existing XAMPP `payroll_db` (same
                schema as the original PHP system) and all of your
                real employees/payroll/audit history is used as-is.

Switching backends is just a Settings change + `reconnect()` — no
code changes required anywhere else in the app, since every other
module talks to the database through plain SQLAlchemy sessions.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from config.settings import get_settings, sqlalchemy_url, DatabaseConfig
from database.models import Base


class DatabaseManager:
    """Singleton-style manager for the active SQLAlchemy engine/session."""

    _instance: Optional["DatabaseManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.engine = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.backend: str = "sqlite"

    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "DatabaseManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = DatabaseManager()
            return cls._instance

    # ------------------------------------------------------------------
    def connect(self, cfg: Optional[DatabaseConfig] = None, create_schema: bool = True) -> None:
        """(Re)connect using the given DatabaseConfig (or the persisted
        settings if none supplied). Safe to call again later to switch
        backends at runtime."""
        cfg = cfg or get_settings().database
        url = sqlalchemy_url(cfg)
        self.backend = cfg.backend

        connect_args = {}
        engine_kwargs = {"pool_pre_ping": True, "future": True}
        if cfg.backend == "sqlite":
            connect_args["check_same_thread"] = False
            engine_kwargs["connect_args"] = connect_args

        self.engine = create_engine(url, **engine_kwargs)

        if cfg.backend == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, future=True,
            expire_on_commit=False,
        )

        if create_schema:
            Base.metadata.create_all(self.engine)
            from database.migrations import run_light_migrations, seed_new_reference_data
            run_light_migrations(self.engine)
            with self.session() as s:
                seed_new_reference_data(s)

    # ------------------------------------------------------------------
    def test_connection(self, cfg: DatabaseConfig) -> tuple[bool, str]:
        """Try connecting with the given config without touching the
        active engine. Returns (ok, message)."""
        try:
            url = sqlalchemy_url(cfg)
            connect_args = {"check_same_thread": False} if cfg.backend == "sqlite" else {}
            test_engine = create_engine(url, connect_args=connect_args)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            test_engine.dispose()
            return True, "Connection successful."
        except SQLAlchemyError as e:
            return False, str(e.__cause__ or e)
        except Exception as e:  # noqa: BLE001
            return False, str(e)

    # ------------------------------------------------------------------
    @contextmanager
    def session(self):
        """Context-managed session: commits on success, rolls back on
        exception, always closes."""
        if self.SessionLocal is None:
            self.connect()
        sess: Session = self.SessionLocal()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def get_session(self) -> Session:
        """Raw session — caller is responsible for commit/close. Handy
        for UI code that wants finer control (e.g. long-lived dialogs)."""
        if self.SessionLocal is None:
            self.connect()
        return self.SessionLocal()


def get_db() -> DatabaseManager:
    return DatabaseManager.instance()
