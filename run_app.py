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

"""Launch GUI or headless sync (for Task Scheduler)."""

from __future__ import annotations

import sys


def main() -> int:
    if "--sync-silent" in sys.argv:
        from agsync.app_config import load_app_config, save_app_config, to_sync_yaml_shape
        from agsync.engine import run_sync

        cfg = load_app_config()
        try:
            sync_cfg = to_sync_yaml_shape(cfg)
        except ValueError:
            return 1
        from agsync.run_log import append_run

        code, lines = run_sync(sync_cfg)
        body = "\n".join(lines) + f"\n\nExit code: {code}"
        append_run("Scheduled sync", body)
        return code

    if "--gui" in sys.argv or len(sys.argv) == 1:
        from agsync.gui import run_gui

        run_gui()
        return 0

    from agsync.__main__ import main as cli_main

    return cli_main([a for a in sys.argv[1:] if a != "--gui"])


if __name__ == "__main__":
    raise SystemExit(main())
