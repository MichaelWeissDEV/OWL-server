"""Application factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from owl.models import OwlError
from sqlalchemy import select
from sqlalchemy.engine import Engine

from owl_server import __version__, access, db
from owl_server import models as m
from owl_server.config import Settings
from owl_server.deps import AppState
from owl_server.ldap_auth import LdapService
from owl_server.oauth import OAuthService
from owl_server.oidc import OidcService
from owl_server.ratelimit import RateLimiter
from owl_server.routes import admin, auth, skills, system

log = logging.getLogger("owl_server")
API = "/api/v1"


class BodyLimitMiddleware:
    """Reject request bodies over the limit - by ``Content-Length`` and while streaming."""

    def __init__(self, app: Callable[..., Any], max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope["headers"]}
        declared = headers.get(b"content-length")
        too_big = JSONResponse({"detail": "Request body too large"}, status_code=413)
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await too_big(scope, receive, send)
            return
        received = 0
        responded = False

        async def guarded_send(message: dict) -> None:
            if not responded:  # after our 413 nothing else may be sent
                await send(message)

        async def limited() -> dict:
            nonlocal received, responded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes and not responded:
                    responded = True
                    await too_big(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited, guarded_send)


class SecurityHeadersMiddleware:
    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def wrapped(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                for key, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                ):
                    if key not in present:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, wrapped)


def ensure_default_registry(engine: Engine, settings: Settings) -> None:
    factory = db.make_session_factory(engine)
    with db.session_scope(factory) as session:
        if (
            session.scalar(select(m.Registry).where(m.Registry.slug == settings.default_registry))
            is None
        ):
            visibility = "public" if settings.mode == "public" else "private"
            session.add(
                m.Registry(
                    slug=settings.default_registry,
                    name="Default registry",
                    description="The default OWL registry",
                    visibility=visibility,
                )
            )


def create_app(
    settings: Settings,
    engine: Engine | None = None,
    oidc_client: httpx.Client | None = None,
    oauth_client: httpx.Client | None = None,
    ldap_connection_factory: Any = None,
) -> FastAPI:
    """Build the API. Migrations are applied first when ``auto_migrate`` is set."""
    if engine is None:
        if settings.auto_migrate:
            db.upgrade(settings.database_url)
        engine = db.make_engine(settings.database_url)
    ensure_default_registry(engine, settings)
    app = FastAPI(
        title="OWL Server",
        version=__version__,
        description="Self-hostable skill registry compatible with the OWL CLI.",
    )
    factory = db.make_session_factory(engine)
    app.state.owl = AppState(
        settings=settings,
        factory=factory,
        limiter=RateLimiter(settings.login_rate_per_minute),
        oidc=OidcService(settings.oidc, oidc_client) if settings.oidc else None,
        oauth=OAuthService(settings.oauth, oauth_client) if settings.oauth else None,
        ldap=LdapService(settings.ldap, ldap_connection_factory) if settings.ldap else None,
    )
    app.state.engine = engine
    with db.session_scope(factory) as session:
        is_open, reason = access.open_state(settings, session)
    if is_open:
        log.warning(
            "OPEN MODE: no authentication - everyone who can reach this server is an administrator (%s). "
            "Secure it in the dashboard (Settings) or set OWL_SERVER_OPEN=false.",
            reason,
        )

    @app.exception_handler(OwlError)
    async def owl_error(_request: Request, exc: OwlError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)  # details only in the log
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    app.include_router(system.router, prefix=API)
    app.include_router(auth.router, prefix=API)
    app.include_router(admin.router, prefix=API)
    app.include_router(skills.router, prefix=API)
    app.include_router(skills.router, prefix="/r/{registry}" + API)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
            allow_headers=["Authorization", "Content-Type", "If-None-Match"],
        )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    return app
