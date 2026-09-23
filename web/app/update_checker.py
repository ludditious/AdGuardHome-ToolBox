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
from urllib.parse import urlparse

import requests

from agsync.dns_resolve import DEFAULT_PUBLIC_DNS, resolve_hostname

DOCKER_PULL_IMAGE = "ghcr.io/ludditious/adguard-home-toolbox:latest"
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


def _version_sort_key(version: str) -> tuple[str, int]:
    """Sort key for YYYY.MM.DD-<run> versions from CI."""
    text = (version or "").strip()
    if not text or text == "unknown":
        return ("", -1)
    date_part, _, tail = text.partition("-")
    run = int(tail) if tail.isdigit() else 0
    return (date_part, run)


def _remote_is_newer(installed: str, remote: str) -> bool:
    return _version_sort_key(remote) > _version_sort_key(installed)


def _fetch_text(url: str) -> str:
    resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": "AdGuardHome-ToolBox-UpdateCheck/1.0"})
    resp.raise_for_status()
    return resp.text.strip()


def _fetch_text_via_resolved_ip(url: str, *, dns_servers: list[str]) -> str:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise requests.RequestException(f"Invalid URL {url!r}")
    ip = resolve_hostname(host, dns_servers=dns_servers)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    direct = f"{parsed.scheme}://{ip}:{port}{path}"
    resp = requests.get(
        direct,
        timeout=FETCH_TIMEOUT,
        headers={
            "User-Agent": "AdGuardHome-ToolBox-UpdateCheck/1.0",
            "Host": host,
        },
    )
    resp.raise_for_status()
    return resp.text.strip()


def _fetch_text_resilient(url: str, *, source_ip: str | None) -> str:
    try:
        return _fetch_text(url)
    except requests.RequestException:
        pass
    groups: list[list[str]] = [list(DEFAULT_PUBLIC_DNS)]
    src = (source_ip or "").strip()
    if src:
        groups.append([src])
    last_exc: Exception | None = None
    for nameservers in groups:
        try:
            return _fetch_text_via_resolved_ip(url, dns_servers=nameservers)
        except (requests.RequestException, OSError) as exc:
            last_exc = exc
    raise requests.RequestException(str(last_exc) if last_exc else "Update check request failed")


def check_for_update(*, source_ip: str | None = None) -> UpdateStatus:
    inst = installed_version()
    base = _raw_base()
    pull = f"docker pull {DOCKER_PULL_IMAGE}"
    try:
        remote_ver = _fetch_text_resilient(f"{base}/version.txt", source_ip=source_ip)
        notes = _fetch_text_resilient(f"{base}/current-release.txt", source_ip=source_ip)
    except requests.RequestException as exc:
        return UpdateStatus(
            installed_version=inst,
            remote_version=None,
            update_available=False,
            pull_command=pull,
            release_notes="",
            error=str(exc),
        )
    update = bool(remote_ver) and _remote_is_newer(inst, remote_ver)
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


def refresh_update_nav_session(session: dict) -> None:
    """Reconcile session flag with version.txt inside this container (after docker pull)."""
    remote = (session.get("update_remote_version") or "").strip()
    if not remote:
        return
    inst = installed_version()
    session["update_available"] = _remote_is_newer(inst, remote)
    session["update_installed_version"] = inst


def session_update_available(session: dict) -> bool:
    refresh_update_nav_session(session)
    return bool(session.get("update_available"))
