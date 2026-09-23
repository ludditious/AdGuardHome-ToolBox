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

"""Encrypt AdGuard Home credentials at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret_key: str) -> Fernet:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(secret_key: str, plain: str) -> str:
    if not plain:
        return ""
    return _fernet(secret_key).encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(secret_key: str, token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet(secret_key).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""
