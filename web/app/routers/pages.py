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

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import get_settings
from ..version import APP_NAME, APP_REVISION, read_bundled_version
from ..update_checker import (
    apply_update_session,
    check_for_update,
    session_update_available,
)
from ..database import get_db
from ..deps import get_current_user
from agsync.client import AdGuardError

from ..backup_service import (
    create_source_backup,
    delete_backup,
    restore_source_backup,
    restore_uploaded_backup,
)
from ..models import CronTickLog, DAY_KEYS, SourceBackup, SyncRunLog, ToolBoxBackup, User
from ..toolbox_backup_service import (
    create_toolbox_backup,
    delete_toolbox_backup,
    restore_toolbox_backup,
    restore_toolbox_upload,
)
from ..schedule_ui import minutes_from_form, parts_from_minutes
from ..auth_constants import SECURITY_QUESTIONS
from ..security import hash_password, hash_recovery_answer, verify_password
from ..services import (
    delete_target,
    ensure_user_defaults,
    execute_sync,
    save_source,
    save_target,
    user_has_recovery,
)
from ..server_address import DEFAULT_ADMIN_PORT, normalize_endpoint, parse_server_url
from ..sync_bridge import plain_password, source_host_ip, test_server, user_dns_servers

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _list_backups(db: Session, user: User) -> list[SourceBackup]:
    return (
        db.query(SourceBackup)
        .filter(SourceBackup.user_id == user.id)
        .order_by(SourceBackup.created_at.desc())
        .limit(12)
        .all()
    )


def _list_toolbox_backups(db: Session, user: User) -> list[ToolBoxBackup]:
    return (
        db.query(ToolBoxBackup)
        .filter(ToolBoxBackup.user_id == user.id)
        .order_by(ToolBoxBackup.created_at.desc())
        .limit(12)
        .all()
    )


def _ctx(request: Request, user: User, db: Session | None = None, **extra):
    settings = get_settings()
    return {
        "request": request,
        "user": user,
        "app_title": settings.app_title,
        "app_name": APP_NAME,
        "app_revision": APP_REVISION,
        "app_version": read_bundled_version(),
        "current_username": user.username,
        "update_available": session_update_available(request.session),
        **extra,
    }


def _format_test_message(res) -> tuple[str, str]:
    """Returns (css_class, display_text)."""
    if res.ok:
        return "notice notice-ok", f"{res.title}\n{res.message}"
    return "notice notice-err", f"{res.title}: {res.message}"


def _save_password_hint(pw_status: str) -> str:
    if pw_status == "updated":
        return "Settings saved. Password stored."
    if pw_status == "missing":
        return "Settings saved. No password stored yet — enter one and Save."
    return "Settings saved. Password unchanged (left blank)."


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    account_ok: str | None = None,
    account_err: str | None = None,
    msg: str | None = None,
):
    ensure_user_defaults(db, user)
    message = None
    message_class = "notice"
    if account_ok and msg:
        message = msg
        message_class = "notice notice-ok"
    elif account_err and msg:
        message = msg
        message_class = "notice notice-err"
    return templates.TemplateResponse(
        request,
        "settings.html",
        _ctx(
            request,
            user,
            db,
            message=message,
            message_class=message_class,
            security_questions=SECURITY_QUESTIONS,
            recovery_configured=user_has_recovery(user),
            check_updates_on_login=user.check_updates_on_login,
        ),
    )


@router.post("/settings/account/password")
def settings_change_password(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    if not verify_password(current_password, user.password_hash):
        return RedirectResponse("/settings?account_err=1&msg=Current%20password%20is%20wrong", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse(
            "/settings?account_err=1&msg=New%20password%20must%20be%208%2B%20characters", status_code=303
        )
    if new_password != confirm_password:
        return RedirectResponse("/settings?account_err=1&msg=New%20passwords%20do%20not%20match", status_code=303)
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/settings?account_ok=1&msg=Password%20updated", status_code=303)


@router.post("/settings/account/recovery")
def settings_set_recovery(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    answer_1: str = Form(""),
    answer_2: str = Form(""),
    answer_3: str = Form(""),
):
    if not all((answer_1.strip(), answer_2.strip(), answer_3.strip())):
        return RedirectResponse("/settings?account_err=1&msg=Answer%20all%20three%20questions", status_code=303)
    user.recovery_answer_1_hash = hash_recovery_answer(answer_1)
    user.recovery_answer_2_hash = hash_recovery_answer(answer_2)
    user.recovery_answer_3_hash = hash_recovery_answer(answer_3)
    db.commit()
    return RedirectResponse("/settings?account_ok=1&msg=Recovery%20answers%20saved", status_code=303)


@router.post("/settings/updates")
def settings_updates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    check_updates_on_login: str | None = Form(None),
):
    user.check_updates_on_login = check_updates_on_login == "on"
    db.commit()
    return RedirectResponse("/settings?account_ok=1&msg=Update%20preferences%20saved", status_code=303)


@router.get("/about", response_class=HTMLResponse)
def about_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(request, "about.html", _ctx(request, user, db))


@router.get("/update", response_class=HTMLResponse)
def update_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    status = check_for_update(source_ip=source_host_ip(user))
    apply_update_session(request.session, status)
    return templates.TemplateResponse(
        request,
        "update.html",
        _ctx(
            request,
            user,
            db,
            installed_version=status.installed_version,
            remote_version=status.remote_version,
            update_available=status.update_available,
            pull_command=status.pull_command,
            release_notes=status.release_notes,
            update_error=status.error,
        ),
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_user_defaults(db, user)
    recent = (
        db.query(SyncRunLog)
        .filter(SyncRunLog.user_id == user.id)
        .order_by(SyncRunLog.started_at.desc())
        .limit(5)
        .all()
    )
    return templates.TemplateResponse(request, "dashboard.html", _ctx(request, user, db, recent=recent))


@router.get("/source", response_class=HTMLResponse)
def source_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    saved: str | None = None,
    pw: str | None = None,
    err: str | None = None,
):
    ensure_user_defaults(db, user)
    src = user.source
    message = None
    message_class = "notice"
    if err:
        message = err
        message_class = "notice notice-err"
    elif saved:
        message = _save_password_hint(pw or "kept")
        message_class = "notice notice-ok" if pw != "missing" else "notice notice-warn"
    pw_plain = plain_password(src.password_enc) if src else ""
    host_ip, admin_port = parse_server_url(src.url if src else "")
    return templates.TemplateResponse(
        request,
        "source.html",
        _ctx(
            request,
            user,
            db,
            source=src,
            password_stored=bool(src and src.password_enc),
            password_plain=pw_plain,
            message=message,
            message_class=message_class,
            host_ip=host_ip,
            admin_port=admin_port,
        ),
    )


@router.post("/source")
def source_save(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    host_ip: str = Form(""),
    admin_port: str = Form(""),
    username: str = Form("admin"),
    password: str = Form(""),
    enabled: str | None = Form(None),
):
    url, err = normalize_endpoint(host_ip, admin_port or DEFAULT_ADMIN_PORT)
    if err:
        return RedirectResponse(f"/source?err={quote(err)}", status_code=303)
    sk = get_settings().secret_key
    pw_status = save_source(db, user, url, username, password, enabled == "on", sk)
    return RedirectResponse(f"/source?saved=1&pw={quote(pw_status)}", status_code=303)


@router.post("/source/test")
def source_test(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    host_ip: str = Form(""),
    admin_port: str = Form(""),
    username: str = Form("admin"),
    password: str = Form(""),
):
    ensure_user_defaults(db, user)
    src = user.source
    verify = user.sync_options.verify_tls if user.sync_options else False
    test_url, err = normalize_endpoint(host_ip, admin_port or DEFAULT_ADMIN_PORT)
    test_user = username.strip() or "admin"
    enc = src.password_enc if src else ""
    if err:
        from agsync.engine import TestResult

        res = TestResult(False, "Invalid address", err)
    else:
        res = test_server(
            test_url,
            test_user,
            enc,
            form_password=password,
            verify_tls=verify,
            dns_servers=user_dns_servers(user),
        )
    message_class, message = _format_test_message(res)
    pw_display = password if password else plain_password(enc)
    ip, port = parse_server_url(test_url) if test_url else (host_ip.strip(), admin_port or DEFAULT_ADMIN_PORT)
    return templates.TemplateResponse(
        request,
        "source.html",
        _ctx(
            request,
            user,
            db,
            source=src,
            password_stored=bool(src and src.password_enc),
            password_plain=pw_display,
            message=message,
            message_class=message_class,
            host_ip=ip,
            admin_port=port,
            form_username=test_user,
        ),
    )


@router.get("/targets", response_class=HTMLResponse)
def targets_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    test_id: int | None = None,
    test_ok: str | None = None,
    test_msg: str | None = None,
    err: str | None = None,
):
    ensure_user_defaults(db, user)
    list_error = err
    test_message = None
    test_message_class = "notice"
    if test_id is not None and test_msg:
        test_message = test_msg
        test_message_class = "notice notice-ok" if test_ok == "1" else "notice notice-err"
    target_pw = {t.id: plain_password(t.password_enc) for t in user.targets}
    target_endpoints = {
        t.id: parse_server_url(t.url) for t in user.targets
    }
    return templates.TemplateResponse(
        request,
        "targets.html",
        _ctx(
            request,
            user,
            db,
            targets=user.targets,
            target_pw=target_pw,
            target_endpoints=target_endpoints,
            test_target_id=test_id,
            test_message=test_message,
            test_message_class=test_message_class,
            default_admin_port=DEFAULT_ADMIN_PORT,
            list_error=list_error,
        ),
    )


@router.post("/targets/add")
def target_add(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    name: str = Form(""),
    host_ip: str = Form(""),
    admin_port: str = Form(""),
    username: str = Form("admin"),
    password: str = Form(""),
    enabled: str | None = Form(None),
):
    url, err = normalize_endpoint(host_ip, admin_port or DEFAULT_ADMIN_PORT)
    if err:
        return RedirectResponse(f"/targets?err={quote(err)}", status_code=303)
    sk = get_settings().secret_key
    save_target(
        db, user, target_id=None, name=name, url=url, username=username,
        password=password, enabled=enabled == "on", sk=sk,
    )
    return RedirectResponse("/targets", status_code=303)


@router.post("/targets/{target_id}/edit")
def target_edit(
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    name: str = Form(""),
    host_ip: str = Form(""),
    admin_port: str = Form(""),
    username: str = Form("admin"),
    password: str = Form(""),
    enabled: str | None = Form(None),
):
    url, err = normalize_endpoint(host_ip, admin_port or DEFAULT_ADMIN_PORT)
    if err:
        return RedirectResponse(f"/targets?err={quote(err)}", status_code=303)
    sk = get_settings().secret_key
    save_target(
        db, user, target_id=target_id, name=name, url=url, username=username,
        password=password, enabled=enabled == "on", sk=sk,
    )
    return RedirectResponse("/targets", status_code=303)


@router.post("/targets/{target_id}/test")
def target_test(
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    name: str = Form(""),
    host_ip: str = Form(""),
    admin_port: str = Form(""),
    username: str = Form("admin"),
    password: str = Form(""),
):
    ensure_user_defaults(db, user)
    tgt = next((t for t in user.targets if t.id == target_id), None)
    verify = user.sync_options.verify_tls if user.sync_options else False
    test_url, err = normalize_endpoint(host_ip, admin_port or DEFAULT_ADMIN_PORT)
    test_user = username.strip() or "admin"
    enc = tgt.password_enc if tgt else ""
    if err:
        from agsync.engine import TestResult

        res = TestResult(False, "Invalid address", err)
    else:
        res = test_server(
            test_url,
            test_user,
            enc,
            form_password=password,
            verify_tls=verify,
            dns_servers=user_dns_servers(user),
        )
    ok = "1" if res.ok else "0"
    detail = f"{res.title}: {res.message}" if not res.ok else f"{res.title} — {res.message.replace(chr(10), ' ')}"
    return RedirectResponse(
        f"/targets?test_id={target_id}&test_ok={ok}&test_msg={quote(detail)}",
        status_code=303,
    )


@router.post("/targets/{target_id}/delete")
def target_delete(
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_target(db, user, target_id)
    return RedirectResponse("/targets", status_code=303)


@router.get("/options", response_class=HTMLResponse)
def options_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_user_defaults(db, user)
    return templates.TemplateResponse(
        request, "options.html", _ctx(request, user, db, options=user.sync_options)
    )


@router.post("/options")
def options_save(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    verify_tls: str | None = Form(None),
    sync_dns: str | None = Form(None),
    sync_filter_lists: str | None = Form(None),
    sync_custom_rules: str | None = Form(None),
    sync_rewrites: str | None = Form(None),
    sync_clients: str | None = Form(None),
    sync_blocked_services: str | None = Form(None),
    sync_parental_safebrowsing_safesearch: str | None = Form(None),
    refresh_lists_after_sync: str | None = Form(None),
    dry_run: str | None = Form(None),
):
    ensure_user_defaults(db, user)
    opt = user.sync_options
    assert opt is not None
    opt.verify_tls = verify_tls == "on"
    opt.sync_dns = sync_dns == "on"
    opt.sync_filter_lists = sync_filter_lists == "on"
    opt.sync_custom_rules = sync_custom_rules == "on"
    opt.sync_rewrites = sync_rewrites == "on"
    opt.sync_clients = sync_clients == "on"
    opt.sync_blocked_services = sync_blocked_services == "on"
    opt.sync_parental_safebrowsing_safesearch = sync_parental_safebrowsing_safesearch == "on"
    opt.refresh_lists_after_sync = refresh_lists_after_sync == "on"
    opt.dry_run = dry_run == "on"
    db.commit()
    return RedirectResponse("/options", status_code=303)


@router.get("/schedule", response_class=HTMLResponse)
def schedule_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_user_defaults(db, user)
    sch = user.schedule
    days = sch.get_days() if sch else set(DAY_KEYS)
    interval_value, interval_unit = parts_from_minutes(sch.interval_minutes if sch else 60)
    cron_ticks = db.query(CronTickLog).order_by(CronTickLog.created_at.desc()).limit(15).all()
    return templates.TemplateResponse(
        request,
        "schedule.html",
        _ctx(
            request,
            user,
            db,
            schedule=sch,
            days=days,
            day_keys=DAY_KEYS,
            interval_value=interval_value,
            interval_unit=interval_unit,
            cron_ticks=cron_ticks,
        ),
    )


@router.post("/schedule")
def schedule_save(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    enabled: str | None = Form(None),
    interval_value: int = Form(60),
    interval_unit: str = Form("minutes"),
    day_sun: str | None = Form(None),
    day_mon: str | None = Form(None),
    day_tue: str | None = Form(None),
    day_wed: str | None = Form(None),
    day_thu: str | None = Form(None),
    day_fri: str | None = Form(None),
    day_sat: str | None = Form(None),
):
    ensure_user_defaults(db, user)
    sch = user.schedule
    assert sch is not None
    sch.enabled = enabled == "on"
    sch.interval_minutes = minutes_from_form(interval_value, interval_unit)
    flags = {
        "sun": day_sun,
        "mon": day_mon,
        "tue": day_tue,
        "wed": day_wed,
        "thu": day_thu,
        "fri": day_fri,
        "sat": day_sat,
    }
    picked = {k for k, v in flags.items() if v == "on"}
    if not picked:
        picked = set(DAY_KEYS)
    sch.set_days(picked)
    db.commit()
    return RedirectResponse("/schedule", status_code=303)


@router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(SyncRunLog)
        .filter(SyncRunLog.user_id == user.id)
        .order_by(SyncRunLog.started_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(request, "logs.html", _ctx(request, user, db, logs=logs))


@router.post("/logs/clear")
def logs_clear(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(SyncRunLog).filter(SyncRunLog.user_id == user.id).delete()
    db.query(CronTickLog).delete()
    db.commit()
    return RedirectResponse("/logs", status_code=303)


@router.get("/backups", response_class=HTMLResponse)
def backups_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ok: str | None = None,
    msg: str | None = None,
):
    ensure_user_defaults(db, user)
    message = msg
    message_class = "notice notice-ok" if ok == "1" else "notice notice-err" if ok == "0" else "notice"
    return templates.TemplateResponse(
        request,
        "backups.html",
        _ctx(
            request,
            user,
            db,
            message=message,
            message_class=message_class,
            footer_backups=_list_backups(db, user),
            toolbox_backups=_list_toolbox_backups(db, user),
        ),
    )


@router.post("/backups/toolbox/create")
def backups_toolbox_create(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    next: str = Form("/backups"),
):
    ensure_user_defaults(db, user)
    dest = next if next.startswith("/") and not next.startswith("//") else "/backups"
    try:
        row = create_toolbox_backup(db, user)
        return RedirectResponse(
            f"{dest}?ok=1&msg={quote(f'ToolBox backup created: {row.name}')}",
            status_code=303,
        )
    except ValueError as e:
        return RedirectResponse(f"{dest}?ok=0&msg={quote(str(e))}", status_code=303)


@router.get("/backups/toolbox/{backup_id}/download")
def backups_toolbox_download(
    backup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(ToolBoxBackup, backup_id)
    if not row or row.user_id != user.id:
        return RedirectResponse("/backups?ok=0&msg=ToolBox%20backup%20not%20found", status_code=303)
    filename = f"{row.name}.json"
    return Response(
        content=row.payload_json,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/backups/toolbox/{backup_id}/restore")
def backups_toolbox_restore(
    backup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_user_defaults(db, user)
    try:
        restore_toolbox_backup(db, user, backup_id)
        return RedirectResponse("/backups?ok=1&msg=ToolBox%20settings%20restored", status_code=303)
    except ValueError as e:
        return RedirectResponse(f"/backups?ok=0&msg={quote(str(e))}", status_code=303)


@router.post("/backups/toolbox/{backup_id}/delete")
def backups_toolbox_delete(
    backup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_toolbox_backup(db, user, backup_id)
        return RedirectResponse("/backups?ok=1&msg=ToolBox%20backup%20deleted", status_code=303)
    except ValueError as e:
        return RedirectResponse(f"/backups?ok=0&msg={quote(str(e))}", status_code=303)


@router.post("/backups/toolbox/restore-upload")
async def backups_toolbox_restore_upload(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    backup_file: UploadFile = File(...),
):
    ensure_user_defaults(db, user)
    try:
        raw = (await backup_file.read()).decode("utf-8")
        restore_toolbox_upload(db, user, raw)
        return RedirectResponse("/backups?ok=1&msg=ToolBox%20settings%20restored%20from%20file", status_code=303)
    except (ValueError, UnicodeDecodeError) as e:
        return RedirectResponse(f"/backups?ok=0&msg={quote(str(e))}", status_code=303)


@router.post("/backups/create")
def backups_create(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    next: str = Form("/backups"),
):
    ensure_user_defaults(db, user)
    dest = next if next.startswith("/") and not next.startswith("//") else "/backups"
    try:
        row = create_source_backup(db, user)
        return RedirectResponse(f"{dest}?ok=1&msg={quote(f'Backup created: {row.name}')}", status_code=303)
    except (ValueError, AdGuardError) as e:
        return RedirectResponse(f"{dest}?ok=0&msg={quote(str(e))}", status_code=303)


@router.get("/backups/{backup_id}/download")
def backups_download(
    backup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SourceBackup, backup_id)
    if not row or row.user_id != user.id:
        return RedirectResponse("/backups?ok=0&msg=Backup%20not%20found", status_code=303)
    filename = f"{row.name}.json"
    return Response(
        content=row.payload_json,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/backups/{backup_id}/restore")
def backups_restore(
    backup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_user_defaults(db, user)
    try:
        lines = restore_source_backup(db, user, backup_id)
        summary = f"Restored to source ({len(lines)} actions)."
        return RedirectResponse(f"/backups?ok=1&msg={quote(summary)}", status_code=303)
    except ValueError as e:
        return RedirectResponse(f"/backups?ok=0&msg={quote(str(e))}", status_code=303)


@router.post("/backups/{backup_id}/delete")
def backups_delete(
    backup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_backup(db, user, backup_id)
        return RedirectResponse("/backups?ok=1&msg=Backup%20deleted", status_code=303)
    except ValueError as e:
        return RedirectResponse(f"/backups?ok=0&msg={quote(str(e))}", status_code=303)


@router.post("/backups/restore-upload")
async def backups_restore_upload(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    backup_file: UploadFile = File(...),
):
    ensure_user_defaults(db, user)
    try:
        raw = (await backup_file.read()).decode("utf-8")
        lines = restore_uploaded_backup(db, user, raw)
        summary = f"Restored from file ({len(lines)} actions)."
        return RedirectResponse(f"/backups?ok=1&msg={quote(summary)}", status_code=303)
    except (ValueError, UnicodeDecodeError) as e:
        return RedirectResponse(f"/backups?ok=0&msg={quote(str(e))}", status_code=303)


@router.post("/sync-now")
def sync_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    execute_sync(db, user, trigger="manual")
    return RedirectResponse("/logs", status_code=303)
