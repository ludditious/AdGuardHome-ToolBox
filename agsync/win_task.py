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

"""Windows Task Scheduler integration via schtasks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .app_config import TASK_NAME


def launcher_command() -> str:
    """Command line for scheduled / headless sync."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --sync-silent'
    root = Path(__file__).resolve().parent.parent
    py = sys.executable
    if py.lower().endswith("python.exe"):
        pyw = str(Path(py).with_name("pythonw.exe"))
        if Path(pyw).is_file():
            py = pyw
    return f'"{py}" "{root / "run_app.py"}" --sync-silent'


def _run_schtasks(args: list[str]) -> tuple[int, str]:
    cmd = ["schtasks"] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except FileNotFoundError:
        return 1, "schtasks.exe not found (requires Windows)."
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def task_exists() -> bool:
    code, _ = _run_schtasks(["/Query", "/TN", TASK_NAME, "/FO", "LIST"])
    return code == 0


def delete_task() -> tuple[bool, str]:
    if not task_exists():
        return True, "No scheduled task to remove."
    code, out = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    if code != 0:
        return False, out or "Failed to delete task."
    return True, "Scheduled task removed."


def create_or_update_task(schedule: dict[str, Any]) -> tuple[bool, str]:
    if not schedule.get("enabled"):
        return delete_task()

    delete_task()

    tr = launcher_command()
    kind = (schedule.get("kind") or "minutes").lower()
    interval = max(1, int(schedule.get("interval") or 1))
    time_str = schedule.get("time") or "03:00"
    dow = (schedule.get("day_of_week") or "MON").upper()

    args = ["/Create", "/TN", TASK_NAME, "/TR", tr, "/F"]

    if kind == "minutes":
        args += ["/SC", "MINUTE", "/MO", str(interval)]
    elif kind == "hours":
        args += ["/SC", "HOURLY", "/MO", str(interval)]
    elif kind == "daily":
        args += ["/SC", "DAILY", "/ST", time_str]
    elif kind == "weekly":
        args += ["/SC", "WEEKLY", "/D", dow, "/ST", time_str]
    else:
        return False, f"Unknown schedule kind: {kind}"

    # Run whether user is logged on or not; use highest available without forcing admin password prompt in GUI
    args += ["/RL", "LIMITED"]

    code, out = _run_schtasks(args)
    if code != 0:
        hint = ""
        if "access" in out.lower() or "denied" in out.lower():
            hint = " Try running the app as Administrator once to create the task."
        return False, (out or "schtasks failed.") + hint
    return True, f"Scheduled task '{TASK_NAME}' created ({kind})."


def query_task_summary() -> str:
    if not task_exists():
        return "No Windows scheduled task."
    code, out = _run_schtasks(["/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"])
    if code != 0:
        return out or "Could not read task."
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Schedule:") or line.startswith("Repeat:") or line.startswith("Next Run Time:"):
            return line
    return "Task exists (see Task Scheduler for details)."
