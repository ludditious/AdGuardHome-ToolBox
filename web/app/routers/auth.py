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

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth_constants import SECURITY_QUESTIONS
from ..config import get_settings
from ..database import get_db
from ..models import User
from ..security import (
    hash_password,
    hash_recovery_answer,
    verify_password,
    verify_recovery_answer,
)
from ..services import ensure_user_defaults, user_has_recovery
from ..sync_bridge import source_host_ip
from ..update_checker import apply_update_session, check_for_update

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _auth_ctx(request: Request, **extra):
    settings = get_settings()
    return {
        "request": request,
        "app_title": settings.app_title,
        "minimal_layout": True,
        "security_questions": SECURITY_QUESTIONS,
        **extra,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", _auth_ctx(request, error=None))


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    name = username.strip()
    user = db.query(User).filter(User.username == name).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            _auth_ctx(request, error="Invalid username or password."),
            status_code=400,
        )
    request.session["user_id"] = user.id
    if user.check_updates_on_login:
        ensure_user_defaults(db, user)
        apply_update_session(request.session, check_for_update(source_ip=source_host_ip(user)))
    else:
        request.session["update_available"] = False
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/recover", response_class=HTMLResponse)
def recover_page(request: Request):
    return templates.TemplateResponse(
        request, "recover.html", _auth_ctx(request, error=None, success=None)
    )


@router.post("/recover")
def recover_submit(
    request: Request,
    username: str = Form(""),
    answer_1: str = Form(""),
    answer_2: str = Form(""),
    answer_3: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not user_has_recovery(user):
        return templates.TemplateResponse(
            request,
            "recover.html",
            _auth_ctx(
                request,
                error="User not found or recovery is not set up. Sign in and use Settings → Account.",
                success=None,
            ),
            status_code=400,
        )
    if not (
        verify_recovery_answer(answer_1, user.recovery_answer_1_hash)
        and verify_recovery_answer(answer_2, user.recovery_answer_2_hash)
        and verify_recovery_answer(answer_3, user.recovery_answer_3_hash)
    ):
        return templates.TemplateResponse(
            request,
            "recover.html",
            _auth_ctx(request, error="One or more answers are incorrect.", success=None),
            status_code=400,
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "recover.html",
            _auth_ctx(request, error="New password must be at least 8 characters.", success=None),
            status_code=400,
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "recover.html",
            _auth_ctx(request, error="Passwords do not match.", success=None),
            status_code=400,
        )
    user.password_hash = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(
        request,
        "recover.html",
        _auth_ctx(request, error=None, success="Password updated. You can sign in now."),
    )


@router.get("/register")
@router.post("/register")
def register_disabled():
    return RedirectResponse("/login", status_code=303)
