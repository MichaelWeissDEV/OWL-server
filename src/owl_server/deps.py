"""Shared FastAPI dependencies: settings, database session, caller identity, registry access."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from owl_server import accounts, security
from owl_server import models as m
from owl_server.config import Settings
from owl_server.oidc import OidcService
from owl_server.permissions import (
    ANONYMOUS,
    Principal,
    at_least,
    effective_role,
    is_server_admin,
)
from owl_server.ratelimit import RateLimiter
from owl_server.repository import SkillRepository


@dataclass
class AppState:
    settings: Settings
    factory: sessionmaker[Session]
    limiter: RateLimiter
    oidc: OidcService | None = None


def app_state(request: Request) -> AppState:
    return request.app.state.owl


def get_session(request: Request) -> Iterator[Session]:
    """One session per request. Handlers commit explicitly; anything uncommitted is rolled back."""
    session = app_state(request).factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def get_principal(
    request: Request, session: SessionDep, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    """Resolve the bearer token (env admin token, API token or login session) to a principal."""
    if not authorization:
        return ANONYMOUS
    scheme, _, secret = authorization.partition(" ")
    secret = secret.strip()
    if scheme.lower() != "bearer" or not secret:
        raise HTTPException(
            401, "Invalid Authorization header", headers={"WWW-Authenticate": "Bearer"}
        )
    settings = app_state(request).settings
    if settings.admin_token and security.same(secret, settings.admin_token):
        return Principal(kind="bootstrap", username="bootstrap-admin", is_admin=True)
    principal = accounts.principal_for_token(session, secret)
    if principal is None:
        raise HTTPException(
            401, "Invalid, expired or revoked token", headers={"WWW-Authenticate": "Bearer"}
        )
    session.commit()  # last_used_at
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def effective_visibility(settings: Settings, registry: m.Registry) -> str:
    """The server mode overrides per-registry visibility (public: all public, private: all private)."""
    if settings.mode == "public":
        return "public"
    if settings.mode == "private":
        return "private"
    return registry.visibility


def deny(principal: Principal) -> HTTPException:
    """No access: anonymous callers are asked to log in, others learn nothing (404)."""
    if not principal.authenticated:
        return HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return HTTPException(404, "Registry not found")


@dataclass
class RegistryContext:
    registry: m.Registry
    role: str
    principal: Principal
    session: Session
    settings: Settings

    @property
    def repo(self) -> SkillRepository:
        return SkillRepository(self.session, self.registry)

    def require(self, needed: str) -> None:
        if not at_least(self.role, needed):
            if not self.principal.authenticated:
                raise HTTPException(
                    401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}
                )
            raise HTTPException(403, f"This action requires the '{needed}' role in this registry")


def load_registry(
    session: Session, settings: Settings, principal: Principal, slug: str
) -> RegistryContext:
    registry = session.scalar(select(m.Registry).where(m.Registry.slug == slug))
    if registry is None:
        raise deny(principal)
    role = effective_role(principal, registry.id, effective_visibility(settings, registry))
    if role is None:
        raise deny(principal)
    return RegistryContext(registry, role, principal, session, settings)


def registry_context(
    request: Request, session: SessionDep, principal: PrincipalDep
) -> RegistryContext:
    settings = app_state(request).settings
    slug = request.path_params.get("registry") or settings.default_registry
    return load_registry(session, settings, principal, slug)


RegistryDep = Annotated[RegistryContext, Depends(registry_context)]


def require_server_admin(principal: PrincipalDep) -> Principal:
    if not principal.authenticated:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if not is_server_admin(principal):
        raise HTTPException(403, "Server administrator rights required")
    return principal


AdminDep = Annotated[Principal, Depends(require_server_admin)]
