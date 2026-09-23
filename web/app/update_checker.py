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

"""Compare installed version.txt to published copy on GitHub."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

DOCKER_PULL_IMAGE = "ghcr.io/ludditious/adguardhome-toolbox:latest"
DEFAULT_RAW_BASE = "https://raw.githubusercontent.com/ludditious/AdGuardHome-ToolBox/main"
FETCH_TIMEOUT = 12


@dataclass(frozen=True)
class UpdateStatus:
    installed_version: str
    remote_version: str | None
    update_available: bool
    pull_command: str
    release_notes: str
    error: str | None = None


def _raw_base() -> str:
    base = (os.environ.get("UPDATE_CHECK_RAW_BASE") or DEFAULT_RAW_BASE).rstrip("/")
    return base


def installed_version() -> str:
    candidates = (
        Path("/app/version.txt"),
        Path(__file__).resolve().parents[2] / "version.txt",
    )
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return "unknown"


def _fetch_text(url: str) -> str:
    resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": "AdGuardHome-ToolBox-UpdateCheck/1.0"})
    resp.raise_for_status()
    return resp.text.strip()


def check_for_update() -> UpdateStatus:
    inst = installed_version()
    base = _raw_base()
    pull = f"docker pull {DOCKER_PULL_IMAGE}"
    try:
        remote_ver = _fetch_text(f"{base}/version.txt")
        notes = _fetch_text(f"{base}/current-release.txt")
    except requests.RequestException as exc:
        return UpdateStatus(
            installed_version=inst,
            remote_version=None,
            update_available=False,
            pull_command=pull,
            release_notes="",
            error=str(exc),
        )
    update = bool(remote_ver) and remote_ver != inst
    return UpdateStatus(
        installed_version=inst,
        remote_version=remote_ver,
        update_available=update,
        pull_command=pull,
        release_notes=notes,
        error=None,
    )


def apply_update_session(session: dict, status: UpdateStatus) -> None:
    session["update_available"] = status.update_available
    session["update_installed_version"] = status.installed_version
    session["update_remote_version"] = status.remote_version or ""
    session["update_release_notes"] = status.release_notes
    session["update_pull_command"] = status.pull_command
    session["update_check_error"] = status.error or ""


def session_update_available(session: dict) -> bool:
    return bool(session.get("update_available"))
