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

"""Run sync from a config dict."""



from __future__ import annotations



from typing import Any



from .client import AdGuardClient, AdGuardError
from .dns_resolve import parse_dns_server_list

from .sync import apply_snapshot





def _dns_list(entry: dict[str, Any]) -> list[str] | None:
    raw = entry.get("dns_servers")
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw or None
    servers = parse_dns_server_list(str(raw))
    return servers or None


def run_sync(

    cfg: dict[str, Any],

    *,

    target_name: str | None = None,

) -> tuple[int, list[str]]:

    """

    Sync source snapshot to enabled targets.

    Returns (exit_code, log_lines).

    """

    lines: list[str] = []

    opts = cfg.get("options") or {}

    verify = bool(opts.get("verify_tls", True))



    src = cfg["source"]

    source_client = AdGuardClient(

        src["url"],

        src["username"],

        src["password"],

        verify_tls=verify,

        dns_servers=_dns_list(src),

        connect_ip=(src.get("connect_ip") or "").strip() or None,

    )



    try:

        lines.append(f"Logging in to source {source_client.base_url}...")

        source_client.login()

        snapshot = source_client.export_snapshot()

        lines.append("Source snapshot exported.")

    except AdGuardError as e:

        lines.append(f"Source error: {e}")

        return 1, lines



    targets = cfg.get("targets") or []

    if target_name:

        targets = [t for t in targets if (t.get("name") or t.get("url")) == target_name]

        if not targets:

            lines.append(f"No target named {target_name!r}.")

            return 1, lines



    exit_code = 0

    for tgt in targets:

        name = tgt.get("name") or tgt["url"]

        lines.append("")

        lines.append(f"=== Target: {name} ({tgt['url']}) ===")

        client = AdGuardClient(

            tgt["url"],

            tgt["username"],

            tgt["password"],

            verify_tls=verify,

            dns_servers=_dns_list(tgt),

            connect_ip=(tgt.get("connect_ip") or "").strip() or None,

        )

        try:

            client.login()

            actions = apply_snapshot(client, snapshot, opts)

            prefix = "[dry-run] " if opts.get("dry_run") else ""

            for line in actions:

                lines.append(f"  {prefix}{line}")

            lines.append(f"  OK: {name}")

        except AdGuardError as e:

            lines.append(f"  FAILED: {e}")

            exit_code = 1



    return exit_code, lines





class TestResult:

    __slots__ = ("ok", "title", "message")



    def __init__(self, ok: bool, title: str, message: str) -> None:

        self.ok = ok

        self.title = title

        self.message = message





def _test_fail(kind: str, url: str, username: str, step: str, detail: str) -> TestResult:

    body = (

        f"Failure type: {kind}\n"

        f"URL tested: {url.strip() or '(empty)'}\n"

        f"Username: {username or 'admin'}\n"

        f"Step: {step}\n\n"

        f"{detail}"

    )

    return TestResult(False, kind, body)



def test_connection(
    url: str,
    username: str,
    password: str,
    *,
    verify_tls: bool,
    dns_servers: list[str] | None = None,
    connect_ip: str | None = None,
) -> TestResult:

    url = (url or "").strip()

    username = (username or "").strip() or "admin"

    if not url:

        return _test_fail("Missing URL", "", username, "—", "Enter the AdGuard Home URL in the URL field.")

    if not (password or "").strip():

        return _test_fail(

            "Missing password",

            url,

            username,

            "—",

            "Password field is empty and nothing is saved.",

        )

    try:

        client = AdGuardClient(
            url,
            username,
            password,
            verify_tls=verify_tls,
            dns_servers=dns_servers,
            connect_ip=connect_ip,
        )

    except AdGuardError as e:

        msg = str(e)

        low = msg.lower()

        if "cannot resolve" in low or "could not resolve" in low:

            return _test_fail("DNS resolution failed", url, username, "resolve hostname", msg)

        return _test_fail("Invalid URL", url, username, "parse URL", msg)

    login_step = f"POST {client.api_root}/login"

    try:

        client.login()

    except AdGuardError as e:

        msg = str(e)

        low = msg.lower()

        if "wrong username" in low or "invalid username" in low or "invalid password" in low:

            return _test_fail("Wrong username or password", client.base_url, username, login_step, msg)

        if "401" in msg or "403" in msg:

            return _test_fail("Wrong username or password", client.base_url, username, login_step, msg)

        if (
            "tcp/network" in low
            or "timed out" in low
            or "connection timed out" in low
            or "dns lookup failed" in low
            or "failed to resolve" in low
        ):

            return _test_fail("Cannot reach server", client.base_url, username, login_step, msg)

        if "tls/ssl" in low or "ssl" in low or "certificate" in low:

            return _test_fail("TLS/SSL error", client.base_url, username, login_step, msg)

        if "web page" in low or "html" in low:

            return _test_fail("Wrong URL (not AdGuard API)", client.base_url, username, login_step, msg)

        if "network error" in low:

            return _test_fail("Network error", client.base_url, username, login_step, msg)

        return _test_fail("Login failed", client.base_url, username, login_step, msg)



    try:

        status = client.get("/status")

    except AdGuardError as e:

        return _test_fail("API error after login", client.base_url, username, f"GET {client.api_root}/status", str(e))



    version = ""

    if isinstance(status, dict):

        version = status.get("version") or status.get("dns_version") or ""

    detail = f"Connected to {client.base_url}"

    if version:

        detail += f"\nAdGuard Home version: {version}"

    return TestResult(True, "Connection OK", detail)

