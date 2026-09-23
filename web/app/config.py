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

"""Web app settings from environment."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_settings() -> "Settings":
    return Settings()


class Settings:
    def __init__(self) -> None:
        self.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
        self.database_url = os.environ.get(
            "DATABASE_URL",
            "sqlite:////data/aghomesync.db",
        )
        self.cron_secret = os.environ.get("CRON_SECRET", "change-cron-secret")
        self.allow_registration = os.environ.get("ALLOW_REGISTRATION", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self.app_title = os.environ.get("APP_TITLE", "AdGuard Home ToolBox")
        self.host = os.environ.get("HOST", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "8080"))
