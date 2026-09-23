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

"""Build sync config from DB models and run agsync engine."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from agsync.dns_resolve import parse_dns_server_list
from agsync.engine import run_sync, test_connection

from .config import get_settings
from .crypto import decrypt
from .models import SourceServer, SyncOptions, TargetServer, User


def _secret() -> str:
    return get_settings().secret_key


def resolve_password(password_enc: str, form_password: str | None) -> tuple[str | None, str | None]:
    """
    Returns (password, error_message).
    error_message if stored password cannot be decrypted.
    """
    if form_password:
        return form_password, None
    if not password_enc:
        return None, "No password saved. Enter the password and click Save, or type it before Test."
    plain = decrypt(_secret(), password_enc)
    if not plain:
        return None, (
            "Saved password could not be read. Re-enter the password and click Save "
            "(this can happen if container encryption keys changed)."
        )
    return plain, None


def options_dict(opt: SyncOptions | None) -> dict[str, Any]:
    if not opt:
        return {
            "verify_tls": False,
            "sync_dns": True,
            "sync_filter_lists": True,
            "sync_custom_rules": True,
            "sync_rewrites": True,
            "sync_clients": True,
            "sync_blocked_services": True,
            "sync_parental_safebrowsing_safesearch": True,
            "refresh_lists_after_sync": True,
            "dry_run": False,
        }
    return {
        "verify_tls": opt.verify_tls,
        "sync_dns": opt.sync_dns,
        "sync_filter_lists": opt.sync_filter_lists,
        "sync_custom_rules": opt.sync_custom_rules,
        "sync_rewrites": opt.sync_rewrites,
        "sync_clients": opt.sync_clients,
        "sync_blocked_services": opt.sync_blocked_services,
        "sync_parental_safebrowsing_safesearch": opt.sync_parental_safebrowsing_safesearch,
        "refresh_lists_after_sync": opt.refresh_lists_after_sync,
        "dry_run": opt.dry_run,
    }


def user_dns_servers(user: User) -> list[str] | None:
    opt = user.sync_options
    if not opt:
        return None
    servers = parse_dns_server_list(opt.dns_servers)
    return servers or None


def build_sync_config(db: Session, user: User) -> dict[str, Any]:
    src: SourceServer | None = user.source
    if not src or not src.enabled:
        raise ValueError("Source server is disabled or not configured.")
    targets = [t for t in user.targets if t.enabled]
    if not targets:
        raise ValueError("No enabled target servers.")

    pw, err = resolve_password(src.password_enc, None)
    if err or not pw:
        raise ValueError(err or "Source password missing.")

    sk = _secret()
    dns = user.sync_options.dns_servers if user.sync_options else ""
    return {
        "source": {
            "url": src.url,
            "username": src.username,
            "password": pw,
            "connect_ip": src.connect_ip or "",
            "dns_servers": dns,
        },
        "targets": [
            {
                "name": t.name or t.url,
                "url": t.url,
                "username": t.username,
                "password": decrypt(sk, t.password_enc) if t.password_enc else "",
                "connect_ip": t.connect_ip or "",
                "dns_servers": dns,
            }
            for t in targets
        ],
        "options": options_dict(user.sync_options),
    }


def run_user_sync(db: Session, user: User) -> tuple[int, list[str]]:
    cfg = build_sync_config(db, user)
    return run_sync(cfg)


def test_server(
    url: str,
    username: str,
    password_enc: str,
    *,
    form_password: str = "",
    verify_tls: bool,
    connect_ip: str = "",
    dns_servers: list[str] | None = None,
):
    url = (url or "").strip()
    if not url:
        from agsync.engine import TestResult

        return TestResult(
            False,
            "Missing URL",
            "Failure type: Missing URL\n\nThe URL field was empty. Type the admin URL in the form and click Test again.",
        )
    password, err = resolve_password(password_enc, form_password or None)
    if err:
        from agsync.engine import TestResult

        return TestResult(False, "Password problem", err)
    if not password:
        from agsync.engine import TestResult

        return TestResult(False, "Missing password", "Password field is empty and nothing is saved.")
    ip = (connect_ip or "").strip() or None
    return test_connection(
        url,
        username,
        password,
        verify_tls=verify_tls,
        dns_servers=dns_servers,
        connect_ip=ip,
    )


def plain_password(password_enc: str) -> str:
    if not password_enc:
        return ""
    return decrypt(_secret(), password_enc)
