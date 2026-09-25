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

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

DAY_KEYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True, default="admin")
    password_hash: Mapped[str] = mapped_column(String(255))
    recovery_answer_1_hash: Mapped[str] = mapped_column(Text, default="")
    recovery_answer_2_hash: Mapped[str] = mapped_column(Text, default="")
    recovery_answer_3_hash: Mapped[str] = mapped_column(Text, default="")
    recovery_answer_1_enc: Mapped[str] = mapped_column(Text, default="")
    recovery_answer_2_enc: Mapped[str] = mapped_column(Text, default="")
    recovery_answer_3_enc: Mapped[str] = mapped_column(Text, default="")
    check_updates_on_login: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[SourceServer | None] = relationship(back_populates="user", uselist=False)
    targets: Mapped[list[TargetServer]] = relationship(back_populates="user")
    sync_options: Mapped[SyncOptions | None] = relationship(back_populates="user", uselist=False)
    schedule: Mapped[SyncSchedule | None] = relationship(back_populates="user", uselist=False)
    run_logs: Mapped[list[SyncRunLog]] = relationship(back_populates="user")
    source_backups: Mapped[list[SourceBackup]] = relationship(back_populates="user")
    toolbox_backups: Mapped[list[ToolBoxBackup]] = relationship(back_populates="user")
    source_backup_settings: Mapped[SourceBackupSettings | None] = relationship(
        back_populates="user", uselist=False
    )


class SourceServer(Base):
    __tablename__ = "source_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    url: Mapped[str] = mapped_column(String(512), default="")
    username: Mapped[str] = mapped_column(String(128), default="admin")
    password_enc: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dns_servers: Mapped[str] = mapped_column(String(512), default="")
    connect_ip: Mapped[str] = mapped_column(String(128), default="")

    user: Mapped[User] = relationship(back_populates="source")


class TargetServer(Base):
    __tablename__ = "target_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    username: Mapped[str] = mapped_column(String(128), default="admin")
    password_enc: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    dns_servers: Mapped[str] = mapped_column(String(512), default="")
    connect_ip: Mapped[str] = mapped_column(String(128), default="")

    user: Mapped[User] = relationship(back_populates="targets")


class SyncOptions(Base):
    __tablename__ = "sync_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_dns: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_filter_lists: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_custom_rules: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_rewrites: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_clients: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_blocked_services: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_parental_safebrowsing_safesearch: Mapped[bool] = mapped_column(Boolean, default=True)
    refresh_lists_after_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    dns_servers: Mapped[str] = mapped_column(String(512), default="")

    user: Mapped[User] = relationship(back_populates="sync_options")


class SyncSchedule(Base):
    __tablename__ = "sync_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    days_json: Mapped[str] = mapped_column(String(128), default='["mon","tue","wed","thu","fri","sat","sun"]')
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="schedule")

    def get_days(self) -> set[str]:
        try:
            data = json.loads(self.days_json)
            if isinstance(data, list):
                return {str(d).lower() for d in data if str(d).lower() in DAY_KEYS}
        except json.JSONDecodeError:
            pass
        return set(DAY_KEYS)

    def set_days(self, days: set[str]) -> None:
        ordered = [d for d in DAY_KEYS if d in days]
        self.days_json = json.dumps(ordered)


class ToolBoxBackup(Base):
    __tablename__ = "toolbox_backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload_json: Mapped[str] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="toolbox_backups")


class SourceBackupSettings(Base):
    __tablename__ = "source_backup_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="source_backup_settings")


class SourceBackup(Base):
    __tablename__ = "source_backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    source_url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    is_automated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    user: Mapped[User] = relationship(back_populates="source_backups")


class CronTickLog(Base):
    __tablename__ = "cron_tick_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    users_due: Mapped[int] = mapped_column(Integer, default=0)
    syncs_ran: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(512), default="")


class SyncRunLog(Base):
    __tablename__ = "sync_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")
    exit_code: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(back_populates="run_logs")
