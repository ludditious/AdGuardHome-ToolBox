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

"""Validate and build http://IP:port AdGuard Home admin URLs."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

DEFAULT_ADMIN_PORT = 3000

_IPV4_INPUT = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def validate_host_ip(text: str) -> str:
    raw = (text or "").strip()
    if not raw or not _IPV4_INPUT.match(raw):
        raise ValueError("Enter a valid IPv4 address (for example 192.168.1.10).")
    try:
        ipaddress.IPv4Address(raw)
    except ValueError as e:
        raise ValueError("Enter a valid IPv4 address (for example 192.168.1.10).") from e
    return raw


def validate_admin_port(text: str) -> int:
    raw = (text or "").strip()
    if not raw.isdigit():
        raise ValueError("Port must be a number between 1 and 65535.")
    port = int(raw)
    if port < 1 or port > 65535:
        raise ValueError("Port must be a number between 1 and 65535.")
    return port


def build_http_url(host_ip: str, port: int) -> str:
    ip = validate_host_ip(host_ip)
    p = validate_admin_port(str(port))
    return f"http://{ip}:{p}"


def parse_server_url(url: str) -> tuple[str, int]:
    """Split stored URL into IPv4 and port; empty ip if not parseable."""
    raw = (url or "").strip()
    if not raw:
        return "", DEFAULT_ADMIN_PORT
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip()
    port = parsed.port or DEFAULT_ADMIN_PORT
    try:
        if host:
            ipaddress.IPv4Address(host)
            return host, port
    except ValueError:
        pass
    return "", port if 1 <= port <= 65535 else DEFAULT_ADMIN_PORT


def normalize_endpoint(host_ip: str, port: int | str) -> tuple[str, str]:
    """Returns (url, error_message). error_message empty on success."""
    try:
        p = validate_admin_port(str(port))
        url = build_http_url(host_ip, p)
        return url, ""
    except ValueError as e:
        return "", str(e)
