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

"""Backup and restore AdGuard Home source settings (no credentials)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from agsync.backup_format import build_backup_document, parse_backup_json
from agsync.client import AdGuardClient, AdGuardError
from agsync.sync import apply_snapshot

from .models import SourceBackup, User
from .sync_bridge import options_dict, plain_password, resolve_password, user_dns_servers


def _source_host_label(url: str) -> str:
    u = (url or "").strip()
    if not u.startswith("http"):
        u = "http://" + u
    host = urlparse(u).hostname or "source"
    return re.sub(r"[^\w.-]+", "-", host).strip("-") or "source"


def backup_display_name(source_url: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    ts = when.strftime("%Y-%m-%d-%H%M%S")
    return f"{_source_host_label(source_url)}-{ts}"


def _source_client(db: Session, user: User) -> AdGuardClient:
    src = user.source
    if not src or not src.enabled:
        raise ValueError("Source server is disabled or not configured.")
    pw, err = resolve_password(src.password_enc, None)
    if err or not pw:
        raise ValueError(err or "Source password missing.")
    verify = user.sync_options.verify_tls if user.sync_options else False
    client = AdGuardClient(
        src.url,
        src.username,
        pw,
        verify_tls=verify,
        dns_servers=user_dns_servers(user),
        connect_ip=(src.connect_ip or "").strip() or None,
    )
    client.login()
    return client


def create_source_backup(db: Session, user: User) -> SourceBackup:
    src = user.source
    assert src is not None
    client = _source_client(db, user)
    snapshot = client.export_snapshot()
    name = backup_display_name(src.url)
    doc = build_backup_document(source_label=name, snapshot=snapshot)
    row = SourceBackup(
        user_id=user.id,
        name=name,
        source_url=client.base_url,
        payload_json=json.dumps(doc, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def restore_source_backup(db: Session, user: User, backup_id: int) -> list[str]:
    row = db.get(SourceBackup, backup_id)
    if not row or row.user_id != user.id:
        raise ValueError("Backup not found.")
    doc = parse_backup_json(row.payload_json)
    client = _source_client(db, user)
    opts = options_dict(user.sync_options)
    opts["dry_run"] = False
    try:
        lines = apply_snapshot(client, doc["snapshot"], opts)
    except AdGuardError as e:
        raise ValueError(str(e)) from e
    return lines


def restore_uploaded_backup(db: Session, user: User, raw: str) -> list[str]:
    doc = parse_backup_json(raw)
    client = _source_client(db, user)
    opts = options_dict(user.sync_options)
    opts["dry_run"] = False
    try:
        lines = apply_snapshot(client, doc["snapshot"], opts)
    except AdGuardError as e:
        raise ValueError(str(e)) from e
    return lines


def delete_backup(db: Session, user: User, backup_id: int) -> None:
    row = db.get(SourceBackup, backup_id)
    if not row or row.user_id != user.id:
        raise ValueError("Backup not found.")
    db.delete(row)
    db.commit()
