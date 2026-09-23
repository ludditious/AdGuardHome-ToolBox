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

import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

_cron_tick_lock = threading.Lock()

from .auth_constants import DEFAULT_PASSWORD, DEFAULT_USERNAME
from .crypto import encrypt
from .cron_logic import users_due_for_sync
from .models import (
    CronTickLog,
    SourceServer,
    SyncOptions,
    SyncRunLog,
    SyncSchedule,
    TargetServer,
    User,
    utcnow,
)
from .security import hash_password
from .sync_bridge import run_user_sync


def ensure_single_user(db: Session) -> User:
    user = db.query(User).order_by(User.id).first()
    if not user:
        user = User(
            email="admin@local",
            username=DEFAULT_USERNAME,
            password_hash=hash_password(DEFAULT_PASSWORD),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if not (user.username or "").strip():
            user.username = DEFAULT_USERNAME
            changed = True
        # First login after upgrade from open 1.2.x: empty password_hash → default credentials once.
        if not user.password_hash or len(user.password_hash) < 20:
            user.password_hash = hash_password(DEFAULT_PASSWORD)
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
    ensure_user_defaults(db, user)
    return user


def user_has_recovery(user: User) -> bool:
    return bool(
        user.recovery_answer_1_hash
        and user.recovery_answer_2_hash
        and user.recovery_answer_3_hash
    )


def ensure_user_defaults(db: Session, user: User) -> None:
    if user.source is None:
        user.source = SourceServer(user_id=user.id)
    if user.sync_options is None:
        user.sync_options = SyncOptions(user_id=user.id)
    if user.schedule is None:
        user.schedule = SyncSchedule(user_id=user.id)
    db.commit()


def run_cron_tick(db: Session) -> dict[str, int]:
    """Check schedules and run due syncs; always records a tick log entry."""
    with _cron_tick_lock:
        return _run_cron_tick_unlocked(db)


def _run_cron_tick_unlocked(db: Session) -> dict[str, int]:
    due = users_due_for_sync(db)
    ran = 0
    errors = 0
    for user in due:
        log = execute_sync(db, user, trigger="cron")
        ran += 1
        if log.exit_code != 0:
            errors += 1
    if ran:
        detail = f"Ran {ran} scheduled sync(s); {errors} failed."
    elif due:
        detail = "Users were due but none ran (unexpected)."
    else:
        detail = "No sync due this minute (schedule off, wrong day, or interval not elapsed)."
    tick = CronTickLog(
        users_due=len(due),
        syncs_ran=ran,
        errors=errors,
        detail=detail,
    )
    db.add(tick)
    db.commit()
    return {"due": len(due), "ran": ran, "errors": errors}


def execute_sync(db: Session, user: User, *, trigger: str) -> SyncRunLog:
    log = SyncRunLog(user_id=user.id, trigger=trigger, started_at=utcnow())
    db.add(log)
    db.commit()
    try:
        code, lines = run_user_sync(db, user)
        log.body = "\n".join(lines)
        log.exit_code = code
    except ValueError as e:
        log.body = str(e)
        log.exit_code = 1
    except Exception as e:
        log.body = f"Unexpected error: {e}"
        log.exit_code = 1
    log.finished_at = datetime.now(timezone.utc)
    if user.schedule and trigger == "cron":
        user.schedule.last_run_at = log.finished_at
    db.commit()
    db.refresh(log)
    return log


def save_source(
    db: Session,
    user: User,
    url: str,
    username: str,
    password: str,
    enabled: bool,
    sk: str,
) -> str:
    """Returns password save status: updated, kept, or missing."""
    ensure_user_defaults(db, user)
    src = user.source
    assert src is not None
    src.url = url.strip()
    src.username = username.strip() or "admin"
    pw_status = "kept"
    if password:
        src.password_enc = encrypt(sk, password)
        pw_status = "updated"
    elif not src.password_enc:
        pw_status = "missing"
    src.enabled = enabled
    src.connect_ip = ""
    src.dns_servers = ""
    db.commit()
    return pw_status


def save_target(
    db: Session,
    user: User,
    *,
    target_id: int | None,
    name: str,
    url: str,
    username: str,
    password: str,
    enabled: bool,
    sk: str,
) -> TargetServer:
    if target_id:
        tgt = db.get(TargetServer, target_id)
        if not tgt or tgt.user_id != user.id:
            raise ValueError("Target not found.")
    else:
        tgt = TargetServer(user_id=user.id, sort_order=len(user.targets))
        db.add(tgt)
    tgt.name = name.strip()
    tgt.url = url.strip()
    tgt.username = username.strip() or "admin"
    if password:
        tgt.password_enc = encrypt(sk, password)
    tgt.enabled = enabled
    tgt.connect_ip = ""
    tgt.dns_servers = ""
    db.commit()
    db.refresh(tgt)
    return tgt


def delete_target(db: Session, user: User, target_id: int) -> None:
    tgt = db.get(TargetServer, target_id)
    if not tgt or tgt.user_id != user.id:
        raise ValueError("Target not found.")
    db.delete(tgt)
    db.commit()
