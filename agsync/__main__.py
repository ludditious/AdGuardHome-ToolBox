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

"""AdGuard Home 1-to-many configuration sync."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .client import AdGuardError
from .engine import run_sync


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync AdGuard Home settings from one source to many targets."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to YAML config (default: config.yaml)",
    )
    parser.add_argument(
        "--export-only",
        metavar="FILE",
        help="Export source snapshot to JSON and exit (no push)",
    )
    parser.add_argument(
        "--target",
        metavar="NAME",
        help="Sync only the target with this name (from config)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open the Windows desktop UI",
    )
    args = parser.parse_args(argv)

    if args.gui:
        from .gui import run_gui

        run_gui()
        return 0

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        print("Copy config.example.yaml to config.yaml and edit it.", file=sys.stderr)
        return 1

    cfg = load_config(cfg_path)
    opts = cfg.get("options") or {}
    verify = bool(opts.get("verify_tls", True))

    from .client import AdGuardClient

    src = cfg["source"]
    source_client = AdGuardClient(
        src["url"],
        src["username"],
        src["password"],
        verify_tls=verify,
    )

    try:
        print(f"Logging in to source {src['url']}...")
        source_client.login()
        snapshot = source_client.export_snapshot()
    except AdGuardError as e:
        print(f"Source error: {e}", file=sys.stderr)
        return 1

    if args.export_only:
        Path(args.export_only).write_text(
            json.dumps(snapshot, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote snapshot to {args.export_only}")
        return 0

    sync_cfg = dict(cfg)
    if args.target:
        sync_cfg["targets"] = [
            t for t in (cfg.get("targets") or []) if t.get("name") == args.target
        ]
        if not sync_cfg["targets"]:
            print(f"No target named {args.target!r}", file=sys.stderr)
            return 1

    exit_code, lines = run_sync(sync_cfg, target_name=args.target)
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
