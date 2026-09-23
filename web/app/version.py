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

"""App metadata — update APP_REVISION when docs or release notes change."""

from pathlib import Path

APP_NAME = "AdGuard Home ToolBox"
APP_REVISION = "2026-09-23e"


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
