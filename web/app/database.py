# Copyright (C) 2026 https://ludditious.com/
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations



from sqlalchemy import create_engine, text

from sqlalchemy.orm import DeclarativeBase, sessionmaker



from .config import get_settings





class Base(DeclarativeBase):

    pass





def _engine():

    settings = get_settings()

    url = settings.database_url

    connect_args = {}

    if url.startswith("sqlite"):

        connect_args["check_same_thread"] = False

    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)





engine = _engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)





def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()





def _sqlite_column_names(conn, table: str) -> set[str]:

    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()

    return {str(r[1]) for r in rows}





def _sqlite_add_column(conn, table: str, column: str, ddl: str) -> None:

    existing = _sqlite_column_names(conn, table)

    if column in existing:

        return

    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))





def migrate_schema() -> None:

    """Add columns introduced after first deploy (create_all does not alter tables)."""

    url = str(engine.url)

    if not url.startswith("sqlite"):

        return

    patches = [

        ("source_servers", "dns_servers", "VARCHAR(512) NOT NULL DEFAULT ''"),

        ("source_servers", "connect_ip", "VARCHAR(128) NOT NULL DEFAULT ''"),

        ("target_servers", "dns_servers", "VARCHAR(512) NOT NULL DEFAULT ''"),

        ("target_servers", "connect_ip", "VARCHAR(128) NOT NULL DEFAULT ''"),

        ("sync_options", "dns_servers", "VARCHAR(512) NOT NULL DEFAULT ''"),
        ("users", "username", "VARCHAR(128) NOT NULL DEFAULT 'admin'"),
        ("users", "recovery_answer_1_hash", "TEXT NOT NULL DEFAULT ''"),
        ("users", "recovery_answer_2_hash", "TEXT NOT NULL DEFAULT ''"),
        ("users", "recovery_answer_3_hash", "TEXT NOT NULL DEFAULT ''"),
        ("users", "recovery_answer_1_enc", "TEXT NOT NULL DEFAULT ''"),
        ("users", "recovery_answer_2_enc", "TEXT NOT NULL DEFAULT ''"),
        ("users", "recovery_answer_3_enc", "TEXT NOT NULL DEFAULT ''"),
        ("users", "check_updates_on_login", "BOOLEAN NOT NULL DEFAULT 0"),
        ("source_backups", "is_automated", "BOOLEAN NOT NULL DEFAULT 0"),

    ]

    with engine.begin() as conn:

        for table, column, ddl in patches:

            try:

                if _sqlite_column_names(conn, table):

                    _sqlite_add_column(conn, table, column, ddl)

            except Exception:

                continue





def init_db() -> None:

    from . import models  # noqa: F401



    Base.metadata.create_all(bind=engine)

    migrate_schema()

