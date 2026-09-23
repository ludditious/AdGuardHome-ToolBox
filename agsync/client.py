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

"""AdGuard Home HTTP API client."""



from __future__ import annotations



import json

import re

from typing import Any
from urllib.parse import urlparse

import requests

from .dns_resolve import prepare_hostname_for_requests





class AdGuardError(RuntimeError):

    pass





def _exception_text(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(str(cur))
        cur = cur.__cause__ or cur.__context__
    return " ".join(parts)


def _connection_failure_message(api_root: str, exc: BaseException) -> str:
    endpoint = f"{api_root}/login"
    low = _exception_text(exc).lower()
    if (
        "failed to resolve" in low
        or "nameresolutionerror" in low
        or "no address associated with hostname" in low
        or "getaddrinfo" in low
        or "name or service not known" in low
        or "nodename nor servname" in low
    ):
        reason = (
            "DNS lookup failed from this app (container or host). "
            "Domain names and IPs are both supported — if the name works in your browser on the PC but not here, "
            "set Source DNS servers or container CUSTOM_DNS to your internal DNS, "
            "set AGH_SYNC_HOST_ALIASES=hostname:ip, or use Connect using IP on the Source form."
        )
    elif "connection refused" in low:
        reason = "Connection refused — nothing is listening on that host and port (wrong port, AdGuard Home stopped, or firewalled)."
    elif "timed out" in low or "timeout" in low:
        reason = "Timed out — host unreachable or blocked by a firewall."
    elif "network is unreachable" in low:
        reason = "Network unreachable from this machine (routing or VPN issue)."
    else:
        reason = str(exc).strip() or "TCP connection failed (host unreachable or port closed)."
    return f"TCP/network failure reaching {endpoint}. {reason}"


def normalize_base_url(url: str) -> str:

    u = (url or "").strip()

    if not u:

        raise AdGuardError("Server URL is empty.")

    if not re.match(r"^https?://", u, re.I):

        u = "http://" + u

    u = u.rstrip("/")

    # Basic sanity: must have a host (domain, IP, or bracketed IPv6)
    host_part = re.sub(r"^https?://", "", u, flags=re.I)
    host_part = host_part.split("/", 1)[0]
    if host_part.startswith("["):
        if "]" not in host_part:
            raise AdGuardError("Invalid IPv6 URL — use http://[address]:port")
    elif not host_part or host_part.startswith(":"):
        raise AdGuardError("URL is missing a hostname or IP address.")

    return u





class AdGuardClient:

    def __init__(

        self,

        base_url: str,

        username: str,

        password: str,

        *,

        verify_tls: bool = True,

        timeout: float = 60.0,

        dns_servers: list[str] | None = None,

        connect_ip: str | None = None,

    ) -> None:

        self.base_url = normalize_base_url(base_url)

        self.api_root = f"{self.base_url}/control"

        self.username = username

        self.password = password

        self.verify_tls = verify_tls

        self.timeout = timeout

        self.session = requests.Session()

        host = urlparse(self.base_url).hostname
        try:
            prepare_hostname_for_requests(
                host,
                dns_servers=dns_servers,
                connect_ip=connect_ip,
            )
        except OSError as e:
            raise AdGuardError(
                f"Cannot resolve hostname {host!r} for {self.base_url}. {e}"
            ) from e

    def login(self) -> None:

        try:

            r = self.session.post(

                f"{self.api_root}/login",

                json={"name": self.username, "password": self.password},

                timeout=self.timeout,

                verify=self.verify_tls,

            )

        except requests.exceptions.SSLError as e:

            raise AdGuardError(

                "TLS/SSL error. Try http:// instead of https://, or turn off "

                "'verify TLS' in Options if using a self-signed certificate."

            ) from e

        except requests.exceptions.ConnectTimeout:

            raise AdGuardError(

                f"Connection timed out reaching {self.api_root}/login. "

                "Check the IP/hostname, port in your URL, and firewall."

            )

        except requests.exceptions.ConnectionError as e:

            raise AdGuardError(_connection_failure_message(self.api_root, e))

        except requests.exceptions.RequestException as e:

            raise AdGuardError(f"Network error: {e}") from e



        if r.status_code == 200:

            if _looks_like_html(r):

                raise AdGuardError(

                    "This URL returned a web page, not the AdGuard Home API. "

                    "Use the web admin address (http(s)://host:port where you open AdGuard Home settings)."

                )

            return



        if r.status_code in (400, 401, 403):

            detail = _message_from_body(r)

            raise AdGuardError(detail or "Wrong username or password.")



        raise AdGuardError(

            f"Login failed (HTTP {r.status_code}). {_message_from_body(r) or _snippet(r.text)}"

        )



    def get(self, path: str, **params: Any) -> Any:

        r = self._request("GET", path, params=params or None)

        self._check(r)

        return _parse_json(r, context=f"GET {path}")



    def post(self, path: str, payload: Any = None) -> Any:

        r = self._request("POST", path, json=payload)

        self._check(r)

        if not r.content:

            return None

        return _parse_json(r, context=f"POST {path}", optional=True)



    def put(self, path: str, payload: Any = None) -> Any:

        r = self._request("PUT", path, json=payload)

        self._check(r)

        if not r.content:

            return None

        return _parse_json(r, context=f"PUT {path}", optional=True)



    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:

        url = f"{self.api_root}{path}"

        try:

            return self.session.request(

                method,

                url,

                timeout=self.timeout,

                verify=self.verify_tls,

                **kwargs,

            )

        except requests.exceptions.SSLError as e:

            raise AdGuardError(

                "TLS/SSL error talking to the API. Adjust URL or disable 'verify TLS' in Options."

            ) from e

        except requests.exceptions.ConnectTimeout:

            raise AdGuardError("Connection timed out while calling the AdGuard Home API.")

        except requests.exceptions.ConnectionError:

            raise AdGuardError("Lost connection to the AdGuard Home server.")

        except requests.exceptions.RequestException as e:

            raise AdGuardError(f"Network error: {e}") from e



    @staticmethod

    def _check(r: requests.Response) -> None:

        if r.status_code < 400:

            return

        if r.status_code in (401, 403):

            raise AdGuardError("Not logged in or session expired. Check username and password.")

        detail = _message_from_body(r) or _snippet(r.text)

        raise AdGuardError(f"HTTP {r.status_code} {r.request.method} {r.request.url}: {detail}")



    def _export_blocked_services_config(self) -> dict[str, Any]:
        """Current blocked-service selection (ids + schedule), not the full service catalog."""
        try:
            data = self.get("/blocked_services/get")
            if isinstance(data, dict):
                return data
        except AdGuardError:
            pass
        try:
            ids = self.get("/blocked_services/list")
            if isinstance(ids, list):
                return {"ids": ids, "schedule": {"time_zone": "Local"}}
        except AdGuardError:
            pass
        return {"ids": [], "schedule": {"time_zone": "Local"}}

    def export_snapshot(self) -> dict[str, Any]:

        snap: dict[str, Any] = {}

        snap["filtering"] = self.get("/filtering/status")

        snap["dns"] = self.get("/dns_info")

        snap["rewrites"] = self.get("/rewrite/list")

        snap["clients"] = self.get("/clients")

        snap["blocked_services"] = self._export_blocked_services_config()

        snap["parental"] = self.get("/parental/status")

        snap["safebrowsing"] = self.get("/safebrowsing/status")

        snap["safesearch"] = self.get("/safesearch/status")

        snap["server_status"] = self.get("/status")

        return snap





def _looks_like_html(r: requests.Response) -> bool:

    ct = (r.headers.get("Content-Type") or "").lower()

    if "html" in ct:

        return True

    text = (r.text or "").lstrip()[:200].lower()

    return text.startswith("<!doctype") or text.startswith("<html")





def _snippet(text: str, limit: int = 200) -> str:

    s = " ".join((text or "").split())

    if not s:

        return "(empty response)"

    if len(s) > limit:

        return s[:limit] + "…"

    return s





def _message_from_body(r: requests.Response) -> str:

    if not r.content:

        return ""

    try:

        data = r.json()

    except ValueError:

        if _looks_like_html(r):

            return (

                "Server returned a web page instead of JSON — wrong URL or not the AdGuard Home admin/API."

            )

        return _snippet(r.text)

    if isinstance(data, dict):

        for key in ("message", "error", "detail", "status"):

            if data.get(key):

                return str(data[key])

    return _snippet(json.dumps(data) if data is not None else "")





def _parse_json(r: requests.Response, *, context: str, optional: bool = False) -> Any:

    if not r.content:

        return None

    try:

        return r.json()

    except ValueError as e:

        if optional:

            return None

        if _looks_like_html(r):

            raise AdGuardError(

                f"{context}: response was HTML, not the AdGuard Home API — check the admin URL."

            ) from e

        raise AdGuardError(

            f"{context}: invalid JSON from server ({e}). "

            f"Response: {_snippet(r.text)}"

        ) from e

