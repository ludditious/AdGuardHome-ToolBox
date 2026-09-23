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

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..services import run_cron_tick

router = APIRouter()


@router.post("/internal/cron/tick")
def cron_tick(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    settings = get_settings()
    expected = f"Bearer {settings.cron_secret}"
    if authorization != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = run_cron_tick(db)
    return {"ok": True, **result}
