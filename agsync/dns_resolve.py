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

"""Resolve hostnames using the container/host system DNS (resolv.conf / getaddrinfo)."""

from __future__ import annotations

import ipaddress
import os
import socket

DEFAULT_PUBLIC_DNS: list[str] = ["1.1.1.1", "8.8.8.8"]

# (host, connect_ip) -> ip
_resolved_hosts: dict[tuple[str, str], str] = {}
_patched = False


def _is_literal_ip(host: str) -> bool:
    h = host.strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _host_aliases() -> dict[str, str]:
    raw = os.environ.get("AGH_SYNC_HOST_ALIASES", "")
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, ip = part.rsplit(":", 1)
        name = name.strip().lower()
        ip = ip.strip()
        if name and ip:
            out[name] = ip
    return out


def parse_dns_server_list(text: str | None) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in text.split(",") if s.strip()]


def _nameservers_from_resolv_conf() -> list[str]:
    servers: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver":
                    ns = parts[1]
                    if ns not in ("127.0.0.11", "127.0.0.53"):
                        servers.append(ns)
    except OSError:
        pass
    return servers


def _resolver_groups(*, dns_servers: list[str] | None = None) -> list[tuple[str, list[str]]]:
    labeled: list[tuple[str, list[str]]] = []
    if dns_servers:
        labeled.append(("ToolBox DNS servers", dns_servers))
    else:
        labeled.append(("default public DNS", list(DEFAULT_PUBLIC_DNS)))
    labeled.extend(_system_resolver_groups())
    return labeled


def _system_resolver_groups() -> list[tuple[str, list[str]]]:
    labeled: list[tuple[str, list[str]]] = []
    from_conf = _nameservers_from_resolv_conf()
    if from_conf:
        labeled.append(("system /etc/resolv.conf", from_conf))

    custom = parse_dns_server_list(os.environ.get("CUSTOM_DNS"))
    if custom:
        labeled.append(("container env CUSTOM_DNS", custom))

    fallback = os.environ.get("AGH_SYNC_DNS_FALLBACK", "").strip()
    if fallback:
        public = parse_dns_server_list(fallback)
        if public:
            labeled.append(("env AGH_SYNC_DNS_FALLBACK", public))

    return labeled


def _resolve_via_dnspython(host: str, *, labeled_groups: list[tuple[str, list[str]]]) -> str:
    import dns.resolver

    if not labeled_groups:
        raise OSError(
            f"Could not resolve {host!r} using system DNS (no nameservers in /etc/resolv.conf). "
            "Fix the container/host resolver, set optional env CUSTOM_DNS, "
            "AGH_SYNC_HOST_ALIASES=host:ip, or Connect using IP on the Source form."
        )
    errors: list[str] = []
    for label, nameservers in labeled_groups:
        res = dns.resolver.Resolver(configure=False)
        res.nameservers = nameservers
        res.timeout = 5
        res.lifetime = 12
        for rtype in ("A", "AAAA"):
            try:
                ans = res.resolve(host, rtype)
                if ans:
                    return str(ans[0])
            except Exception as e:
                errors.append(f"[{label}] {nameservers} ({rtype}): {e}")
    raise OSError(
        f"Could not resolve {host!r} using system DNS. "
        f"Tried: {' | '.join(errors[:8])}"
    )


def resolve_hostname(host: str, *, dns_servers: list[str] | None = None) -> str:
    host = (host or "").strip().lower()
    if not host or _is_literal_ip(host):
        return host.strip("[]")

    aliases = _host_aliases()
    if host in aliases:
        return aliases[host]

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except OSError:
        pass

    return _resolve_via_dnspython(host, labeled_groups=_resolver_groups(dns_servers=dns_servers))


def prepare_hostname_for_requests(
    host: str | None,
    *,
    dns_servers: list[str] | None = None,
    connect_ip: str | None = None,
) -> None:
    if not host or _is_literal_ip(host):
        return
    key = host.lower()
    ip_override = (connect_ip or "").strip()
    cache_key = (key, ip_override)

    if ip_override:
        _resolved_hosts[cache_key] = ip_override
    else:
        _resolved_hosts[cache_key] = resolve_hostname(key, dns_servers=dns_servers)

    _host_connect_ip[key] = _resolved_hosts[cache_key]
    _install_create_connection_patch()


_host_connect_ip: dict[str, str] = {}


def _install_create_connection_patch() -> None:
    global _patched
    if _patched:
        return
    import urllib3.util.connection as urllib3_conn

    original = urllib3_conn.create_connection

    def create_connection(address, *args, **kwargs):
        host, port = address
        mapped = _host_connect_ip.get(str(host).lower())
        if mapped:
            host = mapped
        return original((host, port), *args, **kwargs)

    urllib3_conn.create_connection = create_connection
    _patched = True
