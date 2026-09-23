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

"""Backup and restore AdGuard Home ToolBox app configuration (per user)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import TargetServer, ToolBoxBackup, User
from .services import ensure_user_defaults

CONFIG_FORMAT = "adguardhome-toolbox-config"
CONFIG_VERSION = 1


def toolbox_backup_display_name(when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"toolbox-{when.strftime('%Y-%m-%d-%H%M%S')}"


def _row_dict(obj: Any, *, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


def build_toolbox_config_document(db: Session, user: User) -> dict[str, Any]:
    ensure_user_defaults(db, user)
    src = user.source
    opts = user.sync_options
    sched = user.schedule
    assert src is not None and opts is not None and sched is not None
    targets = sorted(user.targets, key=lambda t: (t.sort_order, t.id))
    return {
        "format": CONFIG_FORMAT,
        "format_version": CONFIG_VERSION,
        "check_updates_on_login": bool(user.check_updates_on_login),
        "source": _row_dict(
            src,
            fields=("url", "username", "password_enc", "enabled", "dns_servers", "connect_ip"),
        ),
        "targets": [
            _row_dict(
                t,
                fields=(
                    "name",
                    "url",
                    "username",
                    "password_enc",
                    "enabled",
                    "sort_order",
                    "dns_servers",
                    "connect_ip",
                ),
            )
            for t in targets
        ],
        "sync_options": _row_dict(
            opts,
            fields=(
                "verify_tls",
                "sync_dns",
                "sync_filter_lists",
                "sync_custom_rules",
                "sync_rewrites",
                "sync_clients",
                "sync_blocked_services",
                "sync_parental_safebrowsing_safesearch",
                "refresh_lists_after_sync",
                "dry_run",
                "dns_servers",
            ),
        ),
        "schedule": _row_dict(
            sched,
            fields=("enabled", "interval_minutes", "days_json"),
        ),
    }


def parse_toolbox_config_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Backup must be a JSON object.")
    if data.get("format") != CONFIG_FORMAT:
        raise ValueError(f"Invalid ToolBox backup format (expected {CONFIG_FORMAT!r}).")
    if data.get("format_version") != CONFIG_VERSION:
        raise ValueError(f"Unsupported ToolBox backup version {data.get('format_version')!r}.")
    for key in ("source", "sync_options", "schedule", "targets"):
        if key not in data:
            raise ValueError(f"ToolBox backup is missing {key!r}.")
    if not isinstance(data["targets"], list):
        raise ValueError("ToolBox backup targets must be a list.")
    return data


def _apply_fields(obj: Any, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for f in fields:
        if f in payload:
            setattr(obj, f, payload[f])


def apply_toolbox_config(db: Session, user: User, doc: dict[str, Any]) -> None:
    ensure_user_defaults(db, user)
    user.check_updates_on_login = bool(doc.get("check_updates_on_login", False))
    src = user.source
    opts = user.sync_options
    sched = user.schedule
    assert src is not None and opts is not None and sched is not None

    _apply_fields(
        src,
        doc["source"],
        ("url", "username", "password_enc", "enabled", "dns_servers", "connect_ip"),
    )
    _apply_fields(
        opts,
        doc["sync_options"],
        (
            "verify_tls",
            "sync_dns",
            "sync_filter_lists",
            "sync_custom_rules",
            "sync_rewrites",
            "sync_clients",
            "sync_blocked_services",
            "sync_parental_safebrowsing_safesearch",
            "refresh_lists_after_sync",
            "dry_run",
            "dns_servers",
        ),
    )
    _apply_fields(
        sched,
        doc["schedule"],
        ("enabled", "interval_minutes", "days_json"),
    )

    for tgt in list(user.targets):
        db.delete(tgt)
    db.flush()

    target_fields = (
        "name",
        "url",
        "username",
        "password_enc",
        "enabled",
        "sort_order",
        "dns_servers",
        "connect_ip",
    )
    for i, row in enumerate(doc["targets"]):
        if not isinstance(row, dict):
            continue
        tgt = TargetServer(user_id=user.id, sort_order=i)
        _apply_fields(tgt, row, target_fields)
        if "sort_order" not in row:
            tgt.sort_order = i
        db.add(tgt)

    db.commit()


def create_toolbox_backup(db: Session, user: User) -> ToolBoxBackup:
    ensure_user_defaults(db, user)
    name = toolbox_backup_display_name()
    doc = build_toolbox_config_document(db, user)
    row = ToolBoxBackup(
        user_id=user.id,
        name=name,
        payload_json=json.dumps(doc, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def restore_toolbox_backup(db: Session, user: User, backup_id: int) -> None:
    row = db.get(ToolBoxBackup, backup_id)
    if not row or row.user_id != user.id:
        raise ValueError("ToolBox backup not found.")
    doc = parse_toolbox_config_json(row.payload_json)
    apply_toolbox_config(db, user, doc)


def restore_toolbox_upload(db: Session, user: User, raw: str) -> None:
    doc = parse_toolbox_config_json(raw)
    apply_toolbox_config(db, user, doc)


def delete_toolbox_backup(db: Session, user: User, backup_id: int) -> None:
    row = db.get(ToolBoxBackup, backup_id)
    if not row or row.user_id != user.id:
        raise ValueError("ToolBox backup not found.")
    db.delete(row)
    db.commit()
