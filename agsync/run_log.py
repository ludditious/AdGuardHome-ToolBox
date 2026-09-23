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

"""Persistent activity log for sync and connection tests."""

from __future__ import annotations

from datetime import datetime

from .app_config import config_dir

ACTIVITY_FILE = "activity.log"


def activity_log_path():
    return config_dir() / ACTIVITY_FILE


def read_activity() -> str:
    path = activity_log_path()
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def clear_activity() -> None:
    path = activity_log_path()
    if path.is_file():
        path.unlink()
    path.write_text("", encoding="utf-8")


def append_run(title: str, body: str) -> None:
    path = activity_log_path()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = (
        f"\n{'=' * 60}\n"
        f"{stamp} — {title}\n"
        f"{'=' * 60}\n"
        f"{body.rstrip()}\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
