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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import SessionLocal, init_db
from .scheduler import start_background_scheduler
from .version import APP_NAME, read_bundled_revision, read_bundled_version
from .routers import auth, internal, pages
from .services import ensure_single_user


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=APP_NAME, version=read_bundled_version())

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        max_age=14 * 86400,
        same_site="lax",
        https_only=False,
    )

    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(internal.router)

    @app.exception_handler(401)
    async def login_required(request: Request, _exc: HTTPException):
        # HTML UI: send browsers to login; API-style callers still get redirect (same app).
        return RedirectResponse("/login", status_code=303)

    @app.get("/")
    async def root(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/dashboard", status_code=307)
        return RedirectResponse("/login", status_code=307)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "adguardhome-toolbox",
            "name": APP_NAME,
            "revision": read_bundled_revision(),
            "version": read_bundled_version(),
        }

    static_dir = __import__("pathlib").Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        db = SessionLocal()
        try:
            ensure_single_user(db)
        finally:
            db.close()
        start_background_scheduler()

    return app


app = create_app()
