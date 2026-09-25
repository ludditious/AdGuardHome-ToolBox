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

"""App metadata — image version comes from version.txt (CI); revised uses the same build number."""

from __future__ import annotations

import re
from pathlib import Path

APP_NAME = "AdGuard Home ToolBox"

_VERSION_FILE_PATTERN = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})-(\d+)$")


def read_bundled_version() -> str:
    for path in (
        Path("/app/version.txt"),
        Path(__file__).resolve().parents[2] / "version.txt",
    ):
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return "unknown"


def revision_from_version(version: str) -> str:
    """Map CI version 2026.09.25-28 → revised label 2026-09-25-28 (no letter suffix)."""
    v = (version or "").strip()
    m = _VERSION_FILE_PATTERN.match(v)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"
    return v or "unknown"


def read_bundled_revision() -> str:
    return revision_from_version(read_bundled_version())
