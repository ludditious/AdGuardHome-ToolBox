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

"""Convert between stored interval_minutes and form fields."""

from __future__ import annotations

MAX_INTERVAL_MINUTES = 7 * 24 * 60


def parts_from_minutes(minutes: int) -> tuple[int, str]:
    m = max(1, int(minutes or 60))
    if m >= 60 and m % 60 == 0:
        return m // 60, "hours"
    return m, "minutes"


def minutes_from_form(value: int, unit: str) -> int:
    v = max(1, int(value or 1))
    u = unit if unit in ("minutes", "hours") else "minutes"
    total = v if u == "minutes" else v * 60
    return max(1, min(MAX_INTERVAL_MINUTES, total))
