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

"""Decide which users should sync on each cron tick."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import DAY_KEYS, SyncSchedule, User

_WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _today_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return _WEEKDAY[now.weekday()]


def schedule_due(schedule: SyncSchedule, now: datetime | None = None) -> bool:
    if not schedule.enabled:
        return False
    now = now or datetime.now(timezone.utc)
    today = _today_key(now)
    if today not in schedule.get_days():
        return False
    interval = max(1, int(schedule.interval_minutes or 1))
    if schedule.last_run_at is None:
        return True
    last = schedule.last_run_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed_min = (now - last).total_seconds() / 60.0
    return elapsed_min >= interval


def users_due_for_sync(db: Session, now: datetime | None = None) -> list[User]:
    now = now or datetime.now(timezone.utc)
    users = db.query(User).all()
    due: list[User] = []
    for user in users:
        if not user.schedule:
            continue
        if schedule_due(user.schedule, now):
            due.append(user)
    return due
