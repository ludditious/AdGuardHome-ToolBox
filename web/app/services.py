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
from .backup_retention import DEFAULT_RETENTION_DAYS
from .backup_service import purge_expired_automated_backups, run_automated_source_backup
from .cron_logic import users_due_for_auto_backup, users_due_for_sync
from .models import (
    CronTickLog,
    SourceBackupSettings,
    SourceServer,
    SyncOptions,
    SyncRunLog,
    SyncSchedule,
    TargetServer,
    User,
    utcnow,
)
from .security import hash_password, verify_password
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


def uses_default_password(user: User | None) -> bool:
    if not user or not user.password_hash:
        return False
    return verify_password(DEFAULT_PASSWORD, user.password_hash)


def user_has_recovery(user: User) -> bool:
    return bool(
        user.recovery_answer_1_hash
        and user.recovery_answer_2_hash
        and user.recovery_answer_3_hash
    )


def recovery_answers_for_display(user: User, secret_key: str) -> list[str]:
    """Plaintext answers for Settings (encrypted at rest)."""
    enc = (
        user.recovery_answer_1_enc,
        user.recovery_answer_2_enc,
        user.recovery_answer_3_enc,
    )
    from .crypto import decrypt

    return [decrypt(secret_key, t) if t else "" for t in enc]


def save_recovery_answers(user: User, answers: tuple[str, str, str], secret_key: str) -> None:
    from .crypto import encrypt
    from .security import hash_recovery_answer

    a1, a2, a3 = (a.strip() for a in answers)
    if not all((a1, a2, a3)):
        raise ValueError("All three recovery answers are required.")
    user.recovery_answer_1_hash = hash_recovery_answer(a1)
    user.recovery_answer_2_hash = hash_recovery_answer(a2)
    user.recovery_answer_3_hash = hash_recovery_answer(a3)
    user.recovery_answer_1_enc = encrypt(secret_key, a1)
    user.recovery_answer_2_enc = encrypt(secret_key, a2)
    user.recovery_answer_3_enc = encrypt(secret_key, a3)


def ensure_user_defaults(db: Session, user: User) -> None:
    if user.source is None:
        user.source = SourceServer(user_id=user.id)
    if user.sync_options is None:
        user.sync_options = SyncOptions(user_id=user.id)
    if user.schedule is None:
        user.schedule = SyncSchedule(user_id=user.id)
    if user.source_backup_settings is None:
        user.source_backup_settings = SourceBackupSettings(
            user_id=user.id,
            retention_days=DEFAULT_RETENTION_DAYS,
        )
    db.commit()


def run_cron_tick(db: Session) -> dict[str, int]:
    """Check schedules and run due syncs; always records a tick log entry."""
    with _cron_tick_lock:
        return _run_cron_tick_unlocked(db)


def _run_cron_tick_unlocked(db: Session) -> dict[str, int]:
    now = utcnow()
    due = users_due_for_sync(db, now)
    ran = 0
    errors = 0
    for user in due:
        log = execute_sync(db, user, trigger="cron")
        ran += 1
        if log.exit_code != 0:
            errors += 1

    backup_due = users_due_for_auto_backup(db, now)
    backups_ran = 0
    backup_errors = 0
    for user in backup_due:
        ensure_user_defaults(db, user)
        settings = user.source_backup_settings
        assert settings is not None
        try:
            run_automated_source_backup(db, user)
            settings.last_run_at = now
            db.commit()
            backups_ran += 1
        except Exception:
            backup_errors += 1
            db.rollback()

    for user in db.query(User).all():
        if not user.source_backup_settings or not user.source_backup_settings.enabled:
            continue
        purge_expired_automated_backups(db, user, user.source_backup_settings.retention_days)

    parts: list[str] = []
    if ran:
        parts.append(f"Ran {ran} scheduled sync(s); {errors} failed.")
    else:
        parts.append("No sync due this minute.")
    if backups_ran:
        parts.append(f"Automated backup(s): {backups_ran}; {backup_errors} failed.")
    elif backup_due:
        parts.append("Automated backup due but none created.")
    detail = " ".join(parts)
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
