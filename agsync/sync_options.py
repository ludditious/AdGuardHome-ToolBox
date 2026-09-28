# Copyright (C) 2026 https://ludditious.com/
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.

"""Sync option keys and defaults (web UI, CLI YAML, restore from backups)."""

from __future__ import annotations

from typing import Any

SYNC_OPTION_KEYS: tuple[str, ...] = (
    "verify_tls",
    "sync_filtering_config",
    "sync_block_lists",
    "sync_allow_lists",
    "sync_custom_rules",
    "sync_dns",
    "sync_rewrites",
    "sync_clients",
    "sync_blocked_services",
    "sync_parental",
    "sync_safebrowsing",
    "sync_safesearch",
    "refresh_lists_after_sync",
    "dry_run",
    # Legacy (CLI / old backups); expanded by normalize_sync_options
    "sync_filter_lists",
    "sync_parental_safebrowsing_safesearch",
)


def default_sync_options() -> dict[str, Any]:
    return {
        "verify_tls": False,
        "sync_filtering_config": True,
        "sync_block_lists": True,
        "sync_allow_lists": True,
        "sync_custom_rules": True,
        "sync_dns": True,
        "sync_rewrites": True,
        "sync_clients": True,
        "sync_blocked_services": True,
        "sync_parental": True,
        "sync_safebrowsing": True,
        "sync_safesearch": True,
        "refresh_lists_after_sync": True,
        "dry_run": False,
    }


def normalize_sync_options(options: dict[str, Any] | None) -> dict[str, Any]:
    base = default_sync_options()
    if not options:
        return base
    merged = {**base, **options}
    legacy_lists = merged.get("sync_filter_lists", True)
    legacy_ps = merged.get("sync_parental_safebrowsing_safesearch", True)
    if "sync_block_lists" not in options:
        merged["sync_block_lists"] = legacy_lists
    if "sync_allow_lists" not in options:
        merged["sync_allow_lists"] = legacy_lists
    if "sync_filtering_config" not in options:
        merged["sync_filtering_config"] = True
    for key in ("sync_parental", "sync_safebrowsing", "sync_safesearch"):
        if key not in options:
            merged[key] = legacy_ps
    return merged
