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

import re
from typing import Any

from .client import AdGuardClient, AdGuardError
from .sync_options import normalize_sync_options


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
    whitelist: bool,
) -> list[str]:
    log: list[str] = []
    for wl in (whitelist,):
        key = "whitelist_filters" if wl else "filters"
        src_list = _normalize_filters(source.get(key))
        tgt_status = client.get("/filtering/status")
        tgt_list = _normalize_filters(tgt_status.get(key))
        src_map = {_filter_key(x, whitelist=wl): x for x in src_list}
        tgt_map = {_filter_key(x, whitelist=wl): x for x in tgt_list}

        for k, entry in tgt_map.items():
            if k not in src_map:
                msg = f"remove {'whitelist ' if wl else ''}list {entry['url']}"
                log.append(msg)
                if not dry_run:
                    client.post("/filtering/remove_url", {
                        "url": entry["url"],
                        "whitelist": wl,
                    })

        for k, entry in src_map.items():
            if k not in tgt_map:
                msg = f"add {'whitelist ' if wl else ''}list {entry['url']}"
                log.append(msg)
                if not dry_run:
                    client.post("/filtering/add_url", {
                        "name": entry["name"] or entry["url"],
                        "url": entry["url"],
                        "whitelist": wl,
                    })
            else:
                tgt = tgt_map[k]
                if tgt["enabled"] != entry["enabled"] or tgt["name"] != entry["name"]:
                    msg = f"update {'whitelist ' if wl else ''}list {entry['url']}"
                    log.append(msg)
                    if not dry_run:
                        client.post("/filtering/set_url", {
                            "url": entry["url"],
                            "whitelist": wl,
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


_DNS_SYNC_SKIP = frozenset(
    {
        "default_local_ptr_upstreams",
        "dns_port",
        "http_port",
        "dhcp_available",
        "running",
        "version",
        "language",
        "start_time",
    }
)

_DNS_UPSTREAM_LIST_KEYS = (
    "bootstrap_dns",
    "upstream_dns",
    "fallback_dns",
    "local_ptr_upstreams",
    "private_upstream",
)


def _dns_upstream_lines(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for line in items:
        s = str(line).strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _is_domain_specific_upstream(line: str) -> bool:
    return line.startswith("[/") and "]" in line


def _split_domain_specific_upstreams(lines: list[str]) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    domain_specific: list[str] = []
    for line in lines:
        if _is_domain_specific_upstream(line):
            domain_specific.append(line)
        else:
            plain.append(line)
    return plain, domain_specific


def _plain_upstreams(lines: list[str]) -> list[str]:
    return [x for x in lines if not _is_domain_specific_upstream(x)]


def _prepare_dns_sync_payload(dns_info: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Make /dns_info from the source safe to POST on Docker/cloud targets."""
    notes: list[str] = []
    payload = {k: v for k, v in dns_info.items() if k not in _DNS_SYNC_SKIP}
    payload.pop("dhcp", None)

    if payload.get("upstream_mode") == "":
        payload["upstream_mode"] = "load_balance"

    for key in _DNS_UPSTREAM_LIST_KEYS:
        if key in payload:
            payload[key] = _dns_upstream_lines(payload.get(key))

    private = payload.pop("private_upstream", None)
    if private:
        local = payload.get("local_ptr_upstreams") or []
        payload["local_ptr_upstreams"] = list(dict.fromkeys([*local, *private]))

    upstream = payload.get("upstream_dns") or []
    up_plain, up_domain = _split_domain_specific_upstreams(upstream)
    if up_domain:
        local = payload.get("local_ptr_upstreams") or []
        payload["local_ptr_upstreams"] = list(dict.fromkeys([*local, *up_domain]))
        notes.append("DNS: moved domain-specific upstream lines out of main upstream list")
    payload["upstream_dns"] = up_plain

    local_ptr = payload.get("local_ptr_upstreams") or []
    if bool(payload.get("use_private_ptr_resolvers")):
        if not _plain_upstreams(local_ptr):
            payload["use_private_ptr_resolvers"] = False
            payload["local_ptr_upstreams"] = []
            notes.append(
                "DNS: disabled private reverse DNS resolvers (no plain private upstreams for this target)"
            )
    elif local_ptr and not _plain_upstreams(local_ptr):
        payload["local_ptr_upstreams"] = []

    return payload, notes


def sync_dns(client: AdGuardClient, dns_info: dict[str, Any], *, dry_run: bool) -> list[str]:
    payload, notes = _prepare_dns_sync_payload(dns_info)
    log = list(notes)
    log.append("apply DNS configuration")
    if dry_run:
        return log
    client.post("/dns_config", payload)
    return log


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


def _client_list_from_snapshot(clients_payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(clients_payload, list):
        return [x for x in clients_payload if isinstance(x, dict)]
    if not isinstance(clients_payload, dict):
        return None
    for key in ("clients", "persistent_clients"):
        val = clients_payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            nested = val.get("clients")
            if isinstance(nested, list):
                return [x for x in nested if isinstance(x, dict)]
    if clients_payload.get("auto_clients") is not None and "clients" not in clients_payload:
        return []
    if "clients" in clients_payload and clients_payload.get("clients") in (None, []):
        return []
    return None


def sync_clients(client: AdGuardClient, clients_payload: dict[str, Any], *, dry_run: bool) -> list[str]:
    log: list[str] = []
    src_clients = _client_list_from_snapshot(clients_payload)
    if src_clients is None:
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


def _target_blocked_service_catalog(client: AdGuardClient) -> set[str]:
    try:
        data = client.get("/blocked_services/all")
    except AdGuardError:
        return set()
    if isinstance(data, dict):
        items = data.get("blocked_services") or data.get("services") or []
    elif isinstance(data, list):
        items = data
    else:
        return set()
    known: set[str] = set()
    for item in items:
        if isinstance(item, str):
            known.add(item)
        elif isinstance(item, dict):
            sid = item.get("id") or item.get("name")
            if isinstance(sid, str) and sid:
                known.add(sid)
    return known


def _filter_blocked_service_ids(
    client: AdGuardClient, ids: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Returns (ids_to_apply, skipped_not_on_target, log_lines)."""
    log: list[str] = []
    known = _target_blocked_service_catalog(client)
    if not known:
        return ids, [], log
    apply_ids = [i for i in ids if i in known]
    skipped = [i for i in ids if i not in known]
    for sid in skipped:
        log.append(f"skip blocked service {sid} (not available on this AdGuard Home version)")
    return apply_ids, skipped, log


def _push_blocked_services(
    client: AdGuardClient, ids: list[str], schedule: dict[str, Any]
) -> None:
    payload = {"ids": ids, "schedule": schedule}
    remaining = list(ids)
    while remaining:
        try:
            client.put("/blocked_services/update", {**payload, "ids": remaining})
            return
        except AdGuardError as e:
            err = str(e)
            if "HTTP 404" in err or "HTTP 405" in err:
                client.post("/blocked_services/set", remaining)
                return
            m = re.search(r'unknown blocked-service\s+"([^"]+)"', err, re.I)
            if m and m.group(1) in remaining:
                remaining.remove(m.group(1))
                continue
            raise


def sync_blocked_services(client: AdGuardClient, data: dict[str, Any], *, dry_run: bool) -> list[str]:
    ids = _blocked_service_id_strings(data)
    schedule = (data or {}).get("schedule") if isinstance(data, dict) else None
    if not schedule:
        schedule = {"time_zone": "Local"}
    apply_ids, _skipped, filter_log = _filter_blocked_service_ids(client, ids)
    log = list(filter_log)
    msg = f"blocked services ({len(apply_ids)} of {len(ids)} selected)"
    log.append(msg)
    if dry_run:
        return log
    if not apply_ids and ids:
        log.append("blocked services: none could be applied on this target (catalog mismatch)")
        return log
    if apply_ids:
        _push_blocked_services(client, apply_ids, schedule)
    return log


def sync_parental(client: AdGuardClient, snap: dict[str, Any], *, dry_run: bool) -> list[str]:
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
    return log


def sync_safebrowsing(client: AdGuardClient, snap: dict[str, Any], *, dry_run: bool) -> list[str]:
    log: list[str] = []
    sb = snap.get("safebrowsing") or {}
    if sb.get("enabled"):
        log.append("enable safebrowsing")
        if not dry_run:
            client.post("/safebrowsing/enable", {})
    else:
        log.append("disable safebrowsing")
        if not dry_run:
            client.post("/safebrowsing/disable", {})
    return log


def sync_safesearch(client: AdGuardClient, snap: dict[str, Any], *, dry_run: bool) -> list[str]:
    log: list[str] = []
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
    opts = normalize_sync_options(options)
    dry_run = bool(opts.get("dry_run"))
    log: list[str] = []
    filtering = snap.get("filtering") or {}

    if opts.get("sync_filtering_config", True):
        log.extend(sync_filtering_config(client, filtering, dry_run=dry_run))

    if opts.get("sync_block_lists", True):
        log.extend(sync_filter_lists(client, filtering, dry_run=dry_run, whitelist=False))

    if opts.get("sync_allow_lists", True):
        log.extend(sync_filter_lists(client, filtering, dry_run=dry_run, whitelist=True))

    if opts.get("sync_custom_rules", True):
        log.extend(sync_custom_rules(client, filtering, dry_run=dry_run))

    if opts.get("sync_dns", True) and snap.get("dns"):
        log.extend(sync_dns(client, snap["dns"], dry_run=dry_run))

    if opts.get("sync_rewrites", True):
        rewrites = snap.get("rewrites") or []
        if isinstance(rewrites, dict):
            rewrites = rewrites.get("rewrites") or []
        log.extend(sync_rewrites(client, rewrites, dry_run=dry_run))

    if opts.get("sync_clients", True) and snap.get("clients") is not None:
        log.extend(sync_clients(client, snap["clients"], dry_run=dry_run))

    if opts.get("sync_blocked_services", True) and snap.get("blocked_services") is not None:
        log.extend(sync_blocked_services(client, snap["blocked_services"], dry_run=dry_run))

    if opts.get("sync_parental", True):
        log.extend(sync_parental(client, snap, dry_run=dry_run))

    if opts.get("sync_safebrowsing", True):
        log.extend(sync_safebrowsing(client, snap, dry_run=dry_run))

    if opts.get("sync_safesearch", True):
        log.extend(sync_safesearch(client, snap, dry_run=dry_run))

    if opts.get("refresh_lists_after_sync", True) and not dry_run:
        client.post("/filtering/refresh", {"whitelist": False})
        client.post("/filtering/refresh", {"whitelist": True})
        log.append("refreshed block/allow filter lists")

    return log
