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

"""Local app configuration (JSON in %LOCALAPPDATA%\\AGHomeSync)."""

from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_DIR_NAME = "AGHomeSync"
CONFIG_FILE = "settings.json"
TASK_NAME = "AGHomeSync"

DEFAULT_OPTIONS: dict[str, Any] = {
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

DEFAULT_SCHEDULE: dict[str, Any] = {
    "enabled": False,
    "kind": "minutes",
    "interval": 30,
    "time": "03:00",
    "day_of_week": "MON",
}

DEFAULT_SOURCE: dict[str, Any] = {
    "url": "http://192.168.1.10:3000",
    "username": "admin",
    "password": "",
    "enabled": True,
}


def config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / CONFIG_FILE


def default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "source": deepcopy(DEFAULT_SOURCE),
        "targets": [],
        "options": deepcopy(DEFAULT_OPTIONS),
        "schedule": deepcopy(DEFAULT_SCHEDULE),
    }


def load_app_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        cfg = default_config()
        save_app_config(cfg)
        return cfg
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _merge_defaults(data)


def save_app_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    base = default_config()
    base["source"] = {**DEFAULT_SOURCE, **(data.get("source") or {})}
    base["options"] = {**DEFAULT_OPTIONS, **(data.get("options") or {})}
    base["schedule"] = {**DEFAULT_SCHEDULE, **(data.get("schedule") or {})}
    base["targets"] = list(data.get("targets") or [])
    for t in base["targets"]:
        if not t.get("id"):
            t["id"] = str(uuid.uuid4())
        t.setdefault("enabled", True)
        t.setdefault("name", "")
        t.setdefault("url", "")
        t.setdefault("username", "admin")
        t.setdefault("password", "")
    return base


def new_target_id() -> str:
    return str(uuid.uuid4())


def to_sync_yaml_shape(cfg: dict[str, Any]) -> dict[str, Any]:
    """Shape used by sync engine (enabled targets only)."""
    src = cfg["source"]
    if not src.get("enabled", True):
        raise ValueError("Source server is disabled.")
    targets = []
    for t in cfg.get("targets") or []:
        if not t.get("enabled", True):
            continue
        targets.append({
            "name": t.get("name") or t.get("url") or "target",
            "url": t["url"],
            "username": t.get("username") or "admin",
            "password": t.get("password") or "",
        })
    if not targets:
        raise ValueError("No enabled target servers.")
    return {
        "source": {
            "url": src["url"],
            "username": src.get("username") or "admin",
            "password": src.get("password") or "",
        },
        "targets": targets,
        "options": cfg.get("options") or DEFAULT_OPTIONS,
    }
