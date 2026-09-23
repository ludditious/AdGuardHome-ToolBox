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

"""Backup file envelope for AdGuard Home settings (no login data)."""

from __future__ import annotations

import json
from typing import Any

FORMAT_ID = "adguardhome-toolbox-backup"
_LEGACY_FORMAT_IDS = frozenset({"adguardhome-sync-backup", FORMAT_ID})
FORMAT_VERSION = 1

_SECRET_KEYS = frozenset(
    {
        "password",
        "password_enc",
        "token",
        "secret",
        "api_key",
        "authorization",
    }
)


def _strip_secrets(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_secrets(v) for k, v in obj.items() if k.lower() not in _SECRET_KEYS}
    if isinstance(obj, list):
        return [_strip_secrets(x) for x in obj]
    return obj


def build_backup_document(*, source_label: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "source_label": source_label,
        "snapshot": _strip_secrets(snapshot),
    }


def validate_backup_document(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Backup must be a JSON object.")
    if data.get("format") not in _LEGACY_FORMAT_IDS:
        raise ValueError(f"Invalid backup format (expected {FORMAT_ID!r}).")
    version = data.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(f"Unsupported backup version {version!r} (expected {FORMAT_VERSION}).")
    snap = data.get("snapshot")
    if not isinstance(snap, dict):
        raise ValueError("Backup is missing a snapshot object.")
    if "filtering" not in snap:
        raise ValueError("Snapshot is missing filtering settings.")
    return data


def parse_backup_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    return validate_backup_document(data)
