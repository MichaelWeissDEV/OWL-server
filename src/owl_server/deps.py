"""Shared FastAPI dependencies: settings, database session, caller identity, registry access."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from owl_server import access, accounts, external, security
from owl_server import models as m
from owl_server.config import Settings
from owl_server.ldap_auth import LdapService
from owl_server.oauth import OAuthService
from owl_server.oidc import OidcService
from owl_server.permissions import (
    ANONYMOUS,
    OPEN,
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
    oauth: OAuthService | None = None
    ldap: LdapService | None = None


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


def _proxy_principal(request: Request, session: Session, settings: Settings) -> Principal | None:
    """Identity asserted by a trusted reverse proxy (Kerberos/SPNEGO, SAML, oauth2-proxy, ...).

    The headers count only together with the shared secret; a request that carries the secret header
    with a wrong value is rejected, one without it is treated as a normal request (and any
    ``X-Remote-User`` it may contain is ignored).
    """
    proxy = settings.proxy
    assert proxy is not None
    supplied = request.headers.get(proxy.secret_header)
    if supplied is None:
        return None
    if not security.same(supplied, proxy.secret):
        raise HTTPException(401, "Invalid proxy credentials")
    username = (request.headers.get(proxy.user_header) or "").strip()
    if not username:
        return None
    raw = request.headers.get(proxy.groups_header) or ""
    groups = [g.strip() for g in raw.split(proxy.groups_separator) if g.strip()]
    try:
        user = external.provision(
            session,
            proxy.mapping,
            provider="proxy",
            subject=username,
            username=username,
            email=request.headers.get(proxy.email_header) or None,
            groups=groups,
            touch=False,
        )
    except external.ExternalLoginError as exc:
        raise HTTPException(exc.status, exc.public) from exc
    session.commit()
    return Principal(
        kind="user",
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        memberships=accounts.memberships_of(session, user.id),
    )


def get_principal(
    request: Request, session: SessionDep, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    """Who is calling: proxy-asserted user, env admin token, API token / session - or, while the
    server is open, everyone (an administrator)."""
    settings = app_state(request).settings
    if settings.proxy:
        asserted = _proxy_principal(request, session, settings)
        if asserted is not None:
            return asserted
    is_open = access.is_open(settings, session)
    if authorization:
        scheme, _, secret = authorization.partition(" ")
        secret = secret.strip()
        found: Principal | None = None
        if scheme.lower() == "bearer" and secret:
            if settings.admin_token and security.same(secret, settings.admin_token):
                found = Principal(kind="bootstrap", username="bootstrap-admin", is_admin=True)
            else:
                found = accounts.principal_for_token(session, secret)
                if found is not None:
                    session.commit()  # last_used_at
        if found is not None:
            return found
        if not is_open:  # in open mode a stale token must not lock anybody out
            detail = (
                "Invalid, expired or revoked token" if secret else "Invalid Authorization header"
            )
            raise HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})
    return OPEN if is_open else ANONYMOUS


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
