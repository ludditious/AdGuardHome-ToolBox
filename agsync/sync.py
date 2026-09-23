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

"""Push a source snapshot to one AdGuard Home instance."""

from __future__ import annotations

from typing import Any

from .client import AdGuardClient


def _filter_key(entry: dict[str, Any], *, whitelist: bool) -> str:
    url = entry.get("url") or entry.get("path") or ""
    return f"{'w' if whitelist else 'b'}:{url}"


def _normalize_filters(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out = []
    for f in items:
        out.append({
            "url": f.get("url") or f.get("path") or "",
            "name": f.get("name") or "",
            "enabled": bool(f.get("enabled", True)),
        })
    return [x for x in out if x["url"]]


def sync_filter_lists(
    client: AdGuardClient,
    source: dict[str, Any],
    *,
    dry_run: bool,
) -> list[str]:
    log: list[str] = []
    for whitelist in (False, True):
        key = "whitelist_filters" if whitelist else "filters"
        src_list = _normalize_filters(source.get(key))
        tgt_status = client.get("/filtering/status")
        tgt_list = _normalize_filters(tgt_status.get(key))
        src_map = {_filter_key(x, whitelist=whitelist): x for x in src_list}
        tgt_map = {_filter_key(x, whitelist=whitelist): x for x in tgt_list}

        for k, entry in tgt_map.items():
            if k not in src_map:
                msg = f"remove {'whitelist ' if whitelist else ''}list {entry['url']}"
                log.append(msg)
                if not dry_run:
                    client.post("/filtering/remove_url", {
                        "url": entry["url"],
                        "whitelist": whitelist,
                    })

        for k, entry in src_map.items():
            if k not in tgt_map:
                msg = f"add {'whitelist ' if whitelist else ''}list {entry['url']}"
                log.append(msg)
                if not dry_run:
                    client.post("/filtering/add_url", {
                        "name": entry["name"] or entry["url"],
                        "url": entry["url"],
                        "whitelist": whitelist,
                    })
            else:
                tgt = tgt_map[k]
                if tgt["enabled"] != entry["enabled"] or tgt["name"] != entry["name"]:
                    msg = f"update {'whitelist ' if whitelist else ''}list {entry['url']}"
                    log.append(msg)
                    if not dry_run:
                        client.post("/filtering/set_url", {
                            "url": entry["url"],
                            "whitelist": whitelist,
                            "data": {
                                "name": entry["name"] or entry["url"],
                                "url": entry["url"],
                                "enabled": entry["enabled"],
                            },
                        })
    return log


def sync_custom_rules(client: AdGuardClient, source: dict[str, Any], *, dry_run: bool) -> list[str]:
    rules = source.get("user_rules") or []
    whitelist = source.get("user_rules_whitelist") or source.get("whitelist_user_rules") or []
    # AGH versions differ; filtering/status often uses user_rules only
    if not whitelist and isinstance(source.get("user_rules"), list):
        pass
    payload = {"rules": rules, "whitelist_rules": whitelist}
    msg = f"set custom rules ({len(rules)} block, {len(whitelist)} allow)"
    if dry_run:
        return [msg]
    client.post("/filtering/set_rules", payload)
    return [msg]


def sync_filtering_config(client: AdGuardClient, source: dict[str, Any], *, dry_run: bool) -> list[str]:
    payload = {
        "enabled": bool(source.get("enabled", True)),
        "interval": int(source.get("interval", 24)),
    }
    msg = f"filtering enabled={payload['enabled']} interval={payload['interval']}h"
    if dry_run:
        return [msg]
    client.post("/filtering/config", payload)
    return [msg]


def sync_dns(client: AdGuardClient, dns_info: dict[str, Any], *, dry_run: bool) -> list[str]:
    # Omit read-only / environment-specific fields if present
    skip = {"default_local_ptr_upstreams"}
    payload = {k: v for k, v in dns_info.items() if k not in skip}
    msg = "apply DNS configuration"
    if dry_run:
        return [msg]
    client.post("/dns_config", payload)
    return [msg]


def sync_rewrites(client: AdGuardClient, rewrites: list[dict[str, Any]], *, dry_run: bool) -> list[str]:
    log: list[str] = []
    current = client.get("/rewrite/list") or []
    for rw in current:
        domain = rw.get("domain")
        if not domain:
            continue
        log.append(f"delete rewrite {domain}")
        if not dry_run:
            client.post("/rewrite/delete", {"domain": domain, "answer": rw.get("answer")})
    for rw in rewrites:
        log.append(f"add rewrite {rw.get('domain')} -> {rw.get('answer')}")
        if not dry_run:
            client.post("/rewrite/add", rw)
    return log


def sync_clients(client: AdGuardClient, clients_payload: dict[str, Any], *, dry_run: bool) -> list[str]:
    log: list[str] = []
    src_clients = clients_payload.get("clients") if isinstance(clients_payload, dict) else clients_payload
    if not isinstance(src_clients, list):
        return ["skip clients (unexpected format)"]

    current = client.get("/clients") or {}
    cur_list = current.get("clients") if isinstance(current, dict) else current
    if not isinstance(cur_list, list):
        cur_list = []

    for c in cur_list:
        name = c.get("name") or c.get("ip") or c.get("ids")
        log.append(f"delete client {name}")
        if not dry_run:
            client.post("/clients/delete", {"name": c["name"]} if c.get("name") else {"ip": c["ip"]})

    for c in src_clients:
        log.append(f"add client {c.get('name') or c.get('ip')}")
        if not dry_run:
            client.post("/clients/add", c)
    return log


def _blocked_service_id_strings(data: dict[str, Any] | list[Any] | None) -> list[str]:
    """Extract service names only — never sync icon/rules catalog blobs."""
    if data is None:
        return []
    if isinstance(data, list):
        raw = data
    else:
        raw = data.get("ids") or data.get("blocked_services") or []
        # /blocked_services/all wraps catalog under "blocked_services" as objects
        if not raw and isinstance(data.get("blocked_services"), list):
            raw = data["blocked_services"]
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            sid = item.get("id") or item.get("name")
            if sid and isinstance(sid, str):
                out.append(sid)
    return out


def sync_blocked_services(client: AdGuardClient, data: dict[str, Any], *, dry_run: bool) -> list[str]:
    ids = _blocked_service_id_strings(data)
    schedule = (data or {}).get("schedule") if isinstance(data, dict) else None
    if not schedule:
        schedule = {"time_zone": "Local"}
    payload = {"ids": ids, "schedule": schedule}
    msg = f"blocked services ({len(ids)} selected)"
    if dry_run:
        return [msg]
    try:
        client.put("/blocked_services/update", payload)
    except AdGuardError as e:
        err = str(e)
        if "HTTP 404" in err or "HTTP 405" in err:
            # Older AdGuard Home: POST /set expects a bare JSON array of id strings.
            client.post("/blocked_services/set", ids)
        else:
            raise
    return [msg]


def sync_parental_safe(client: AdGuardClient, snap: dict[str, Any], *, dry_run: bool) -> list[str]:
    log: list[str] = []
    parental = snap.get("parental") or {}
    if parental.get("enabled"):
        log.append("enable parental")
        if not dry_run:
            client.post("/parental/enable", {})
    else:
        log.append("disable parental")
        if not dry_run:
            client.post("/parental/disable", {})

    sb = snap.get("safebrowsing") or {}
    if sb.get("enabled"):
        log.append("enable safebrowsing")
        if not dry_run:
            client.post("/safebrowsing/enable", {})
    else:
        log.append("disable safebrowsing")
        if not dry_run:
            client.post("/safebrowsing/disable", {})

    ss = snap.get("safesearch") or {}
    if ss.get("enabled"):
        log.append("enable safesearch")
        if not dry_run:
            client.post("/safesearch/enable", {})
        settings = ss.get("settings") or ss
        if settings and not dry_run:
            client.put("/safesearch/settings", settings)
    else:
        log.append("disable safesearch")
        if not dry_run:
            client.post("/safesearch/disable", {})
    return log


def apply_snapshot(
    client: AdGuardClient,
    snap: dict[str, Any],
    options: dict[str, Any],
) -> list[str]:
    dry_run = bool(options.get("dry_run"))
    log: list[str] = []
    filtering = snap.get("filtering") or {}

    log.extend(sync_filtering_config(client, filtering, dry_run=dry_run))

    if options.get("sync_filter_lists", True):
        log.extend(sync_filter_lists(client, filtering, dry_run=dry_run))

    if options.get("sync_custom_rules", True):
        log.extend(sync_custom_rules(client, filtering, dry_run=dry_run))

    if options.get("sync_dns", True) and snap.get("dns"):
        log.extend(sync_dns(client, snap["dns"], dry_run=dry_run))

    if options.get("sync_rewrites", True):
        rewrites = snap.get("rewrites") or []
        if isinstance(rewrites, dict):
            rewrites = rewrites.get("rewrites") or []
        log.extend(sync_rewrites(client, rewrites, dry_run=dry_run))

    if options.get("sync_clients", True) and snap.get("clients") is not None:
        log.extend(sync_clients(client, snap["clients"], dry_run=dry_run))

    if options.get("sync_blocked_services", True) and snap.get("blocked_services") is not None:
        log.extend(sync_blocked_services(client, snap["blocked_services"], dry_run=dry_run))

    if options.get("sync_parental_safebrowsing_safesearch", True):
        log.extend(sync_parental_safe(client, snap, dry_run=dry_run))

    if options.get("refresh_lists_after_sync", True) and not dry_run:
        client.post("/filtering/refresh", {"whitelist": False})
        client.post("/filtering/refresh", {"whitelist": True})
        log.append("refreshed block/allow filter lists")

    return log
