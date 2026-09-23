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

"""In-process schedule runner (reliable in Docker; no system cron required)."""

from __future__ import annotations

import logging
import os
import threading
import time

from .database import SessionLocal
from .services import run_cron_tick

logger = logging.getLogger(__name__)

_tick_lock = threading.Lock()
_started = False


def _scheduler_loop() -> None:
    time.sleep(15)
    while True:
        try:
            with _tick_lock:
                db = SessionLocal()
                try:
                    run_cron_tick(db)
                finally:
                    db.close()
        except Exception:
            logger.exception("Scheduler tick failed")
        time.sleep(60)


def start_background_scheduler() -> None:
    global _started
    if _started:
        return
    enabled = os.environ.get("ENABLE_SCHEDULER", "true").lower()
    if enabled in ("0", "false", "no"):
        logger.info("Built-in scheduler disabled (ENABLE_SCHEDULER=%s)", enabled)
        return
    _started = True
    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="agh-sync-scheduler")
    thread.start()
    logger.info("Built-in scheduler started (checks every 60 seconds)")
