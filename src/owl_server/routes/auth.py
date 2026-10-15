"""Login, sessions, personal tokens and (optional) OpenID Connect."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from owl_server import access, accounts, audit, external
from owl_server import models as m
from owl_server.deps import PrincipalDep, SessionDep, app_state, client_ip
from owl_server.ldap_auth import LdapError
from owl_server.oidc import OidcError
from owl_server.permissions import ROLES, is_server_admin

log = logging.getLogger("owl_server")
router = APIRouter(prefix="/auth")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _session_response(session: Session, request: Request, user: m.User) -> dict[str, Any]:
    ttl = app_state(request).settings.session_ttl_hours
    secret, row = accounts.create_token(
        session, name="login session", role="reader", user=user, kind="session", ttl_hours=ttl
    )
    return {
        "token": secret,
        "expires_at": row.expires_at,
        "user": {"username": user.username, "is_admin": user.is_admin},
    }


def _limit(request: Request, key: str) -> None:
    if not app_state(request).limiter.allow(f"{client_ip(request)}:{key}"):
        raise HTTPException(
            429, "Too many attempts, please wait a minute", headers={"Retry-After": "60"}
        )


@router.get("/config")
def auth_config(request: Request, session: SessionDep) -> dict[str, Any]:
    """What the login page needs: whether the server is open and which sign-in methods exist."""
    state = app_state(request)
    settings = state.settings
    is_open, reason = access.open_state(settings, session)
    providers = []
    if settings.oidc:
        providers.append({"id": "oidc", "type": "oidc", "label": settings.oidc.label})
    if settings.oauth:
        providers.append({"id": "oauth", "type": "oauth2", "label": settings.oauth.label})
    return {
        "open": is_open,
        "open_reason": reason,
        "mode": settings.mode,
        "local_accounts": settings.local_accounts,
        "ldap": {"label": settings.ldap.label} if settings.ldap else None,
        "proxy": settings.proxy is not None,
        "providers": providers,
        # kept for older clients
        "oidc": settings.oidc is not None,
    }


@router.post("/login")
def login(
    request: Request,
    response: Response,
    session: SessionDep,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Password login: a local account first, then the directory (LDAP / Active Directory)."""
    state = app_state(request)
    settings = state.settings
    if not settings.local_accounts and state.ldap is None:
        raise HTTPException(404, "Password login is not enabled on this server")
    username, password = str(body.get("username", "")).strip(), str(body.get("password", ""))
    _limit(request, "login")
    _limit(request, f"login:{username.lower()}")
    user = None
    local = accounts.get_user(session, username)
    if settings.local_accounts and (local is None or local.provider == "local"):
        user = accounts.authenticate_password(session, username, password)
    if user is None and state.ldap is not None and (local is None or local.provider == "ldap"):
        user = _ldap_login(state, session, username, password)
    if user is None:
        audit.record(
            session, "anonymous", "auth.login_failed", username[:100], ip=client_ip(request)
        )
        session.commit()
        raise HTTPException(401, "Wrong username or password")
    audit.record(
        session,
        f"user:{user.username}",
        "auth.login",
        f"via {user.provider}",
        ip=client_ip(request),
    )
    result = _session_response(session, request, user)
    session.commit()
    _no_store(response)
    return result


def _ldap_login(state, session: Session, username: str, password: str) -> m.User | None:  # type: ignore[no-untyped-def]
    try:
        identity = state.ldap.authenticate(username, password)
    except LdapError as exc:
        log.warning("LDAP problem: %s", exc)
        raise HTTPException(502, "The directory is not reachable") from exc
    if identity is None:
        return None
    try:
        return external.provision(
            session,
            state.settings.ldap.mapping,
            provider="ldap",
            subject=identity.dn.lower(),
            username=identity.username,
            email=identity.email,
            groups=identity.groups,
        )
    except external.ExternalLoginError as exc:
        raise HTTPException(exc.status, exc.public) from exc


@router.post("/logout")
def logout(request: Request, session: SessionDep, principal: PrincipalDep) -> dict[str, bool]:
    header = request.headers.get("authorization", "")
    secret = header.partition(" ")[2].strip()
    from owl_server import security

    row = session.scalar(
        select(m.ApiToken).where(m.ApiToken.token_hash == security.hash_token(secret))
    )
    if row is not None and row.kind == "session":
        row.revoked_at = m.now()
        audit.record(session, principal, "auth.logout", ip=client_ip(request))
        session.commit()
    return {"ok": True}


@router.get("/me")
def me(
    request: Request, session: SessionDep, principal: PrincipalDep, response: Response
) -> dict[str, Any]:
    _no_store(response)
    memberships = []
    for registry_id, role in principal.memberships:
        registry = session.get(m.Registry, registry_id)
        if registry:
            memberships.append({"registry": registry.slug, "role": role})
    return {
        "authenticated": principal.authenticated,
        "kind": principal.kind,
        "username": principal.username,
        "is_admin": is_server_admin(principal),
        "memberships": memberships,
        "token_role": principal.token_role,
    }


@router.post("/password")
def change_password(
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, bool]:
    if principal.kind != "user" or principal.user_id is None:
        raise HTTPException(403, "Only logged-in local users can change their password")
    user = session.get(m.User, principal.user_id)
    assert user is not None
    _limit(request, f"password:{user.username}")
    try:
        accounts.change_password(session, user, str(body.get("old", "")), str(body.get("new", "")))
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(session, principal, "auth.password_changed", ip=client_ip(request))
    session.commit()
    return {"ok": True}


# -- personal API tokens ------------------------------------------------------------------------


def _token_dict(row: m.ApiToken, registries: dict[int, str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "role": row.role,
        "registry": registries.get(row.registry_id) if row.registry_id else None,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "last_used_at": row.last_used_at,
    }


@router.get("/tokens")
def list_tokens(session: SessionDep, principal: PrincipalDep) -> list[dict[str, Any]]:
    if principal.kind != "user":
        raise HTTPException(403, "Only logged-in users have personal tokens")
    registries = {r.id: r.slug for r in session.scalars(select(m.Registry))}
    rows = session.scalars(
        select(m.ApiToken)
        .where(m.ApiToken.user_id == principal.user_id, m.ApiToken.kind == "api")
        .order_by(m.ApiToken.id)
    )
    return [_token_dict(r, registries) for r in rows]


@router.post("/tokens", status_code=201)
def create_token(
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Create a personal token. Its role can never exceed your own role."""
    if principal.kind != "user" or principal.user_id is None:
        raise HTTPException(403, "Only logged-in users can create personal tokens")
    if principal.token_role is not None:
        raise HTTPException(403, "Log in with your password to create tokens")
    user = session.get(m.User, principal.user_id)
    assert user is not None
    role = str(body.get("role", "reader"))
    registry = None
    slug = body.get("registry")
    if slug:
        registry = session.scalar(select(m.Registry).where(m.Registry.slug == str(slug)))
        if registry is None:
            raise HTTPException(404, "Registry not found")
    if role not in ROLES:
        raise HTTPException(422, f"role must be one of: {', '.join(ROLES)}")
    if role == "admin" and not user.is_admin:
        raise HTTPException(403, "You cannot create a token stronger than your own rights")
    if role != "admin" and not user.is_admin and registry is not None:
        have = dict(principal.memberships).get(registry.id)
        if have is None or ROLES.index(role) > ROLES.index(have):
            raise HTTPException(403, "You cannot create a token stronger than your own rights")
    ttl = body.get("ttl_hours")
    try:
        secret, row = accounts.create_token(
            session,
            name=str(body.get("name", "token")),
            role=role,
            user=user,
            registry=registry,
            ttl_hours=float(ttl) if ttl else None,
        )
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(
        session, principal, "token.create", f"{row.prefix}", f"role={role}", client_ip(request)
    )
    session.commit()
    registries = {r.id: r.slug for r in session.scalars(select(m.Registry))}
    return {"token": secret, **_token_dict(row, registries)}


@router.delete("/tokens/{token_id}")
def revoke_token(
    request: Request, session: SessionDep, principal: PrincipalDep, token_id: int
) -> dict[str, bool]:
    row = session.get(m.ApiToken, token_id)
    if (
        row is None
        or principal.kind != "user"
        or (row.user_id != principal.user_id and not is_server_admin(principal))
    ):
        raise HTTPException(404, "Token not found")
    accounts.revoke_token(session, token_id)
    audit.record(session, principal, "token.revoke", row.prefix, ip=client_ip(request))
    session.commit()
    return {"revoked": True}


# -- single sign-on: OpenID Connect and OAuth 2.0 ---------------------------------------------------


def _sso_service(request: Request, provider: str):  # type: ignore[no-untyped-def]
    state = app_state(request)
    service = {"oidc": state.oidc, "oauth": state.oauth}.get(provider)
    if service is None:
        raise HTTPException(404, "This sign-in method is not configured on this server")
    return service


def _sso_begin(request: Request, session: Session, provider: str, as_json: bool):  # type: ignore[no-untyped-def]
    _limit(request, "sso")
    service = _sso_service(request, provider)
    try:
        url = service.begin(session)
    except OidcError as exc:
        raise HTTPException(exc.status, exc.public) from exc
    session.commit()
    return {"authorization_url": url} if as_json else RedirectResponse(url, status_code=302)


def _sso_complete(
    request: Request, session: Session, provider: str, code: str, state: str
) -> dict[str, Any]:
    service = _sso_service(request, provider)
    settings = app_state(request).settings
    try:
        if provider == "oidc":
            claims = service.complete(session, code, state)
            cfg = settings.oidc
            assert cfg is not None
            subject = str(claims["sub"])
            username = str(claims.get(cfg.username_claim) or claims.get("email") or claims["sub"])
            email, groups, mapping = claims.get("email"), service.claim_values(claims), cfg.mapping
        else:
            profile = service.complete(session, code, state)
            oauth_cfg = settings.oauth
            assert oauth_cfg is not None
            subject = str(profile[oauth_cfg.id_field])
            username = str(profile.get(oauth_cfg.username_field) or subject)
            email = profile.get(oauth_cfg.email_field)
            raw = profile.get(oauth_cfg.groups_field) if oauth_cfg.groups_field else []
            groups = [str(g) for g in raw] if isinstance(raw, list) else ([str(raw)] if raw else [])
            mapping = oauth_cfg.mapping
            if oauth_cfg.allowed_users and username.lower() not in {
                u.lower() for u in oauth_cfg.allowed_users
            }:
                audit.record(
                    session, "anonymous", "auth.oauth_denied", username[:100], ip=client_ip(request)
                )
                session.commit()
                raise HTTPException(403, "This account is not allowed to sign in")
    except OidcError as exc:
        audit.record(
            session,
            "anonymous",
            f"auth.{provider}_failed",
            detail=str(exc)[:300],
            ip=client_ip(request),
        )
        session.commit()
        raise HTTPException(exc.status, exc.public) from exc
    try:
        user = external.provision(
            session,
            mapping,
            provider=provider,
            subject=subject,
            username=username,
            email=email,
            groups=groups,
        )
    except external.ExternalLoginError as exc:
        raise HTTPException(exc.status, exc.public) from exc
    audit.record(session, f"user:{user.username}", f"auth.{provider}_login", ip=client_ip(request))
    result = _session_response(session, request, user)
    session.commit()
    return result


@router.get("/sso/{provider}/login")
def sso_login(
    request: Request,
    session: SessionDep,
    provider: str,
    as_json: Annotated[bool, Query(alias="json")] = False,
):  # type: ignore[no-untyped-def]
    """Start a single sign-on: redirect to the provider (or return the URL with ``?json=1``)."""
    return _sso_begin(request, session, provider, as_json)


@router.get("/sso/{provider}/callback")
def sso_callback(
    request: Request, response: Response, session: SessionDep, provider: str, code: str, state: str
) -> dict[str, Any]:
    _no_store(response)
    return _sso_complete(request, session, provider, code, state)


@router.post("/sso/{provider}/exchange")
def sso_exchange(
    request: Request,
    response: Response,
    session: SessionDep,
    provider: str,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """For single-page apps: the redirect lands in the dashboard, which posts ``code`` and ``state``."""
    _no_store(response)
    return _sso_complete(
        request, session, provider, str(body.get("code", "")), str(body.get("state", ""))
    )


# the original OIDC paths keep working
@router.get("/oidc/login")
def oidc_login(
    request: Request, session: SessionDep, as_json: Annotated[bool, Query(alias="json")] = False
):  # type: ignore[no-untyped-def]
    return _sso_begin(request, session, "oidc", as_json)


@router.get("/oidc/callback")
def oidc_callback(
    request: Request, response: Response, session: SessionDep, code: str, state: str
) -> dict[str, Any]:
    _no_store(response)
    return _sso_complete(request, session, "oidc", code, state)


@router.post("/oidc/exchange")
def oidc_exchange(
    request: Request,
    response: Response,
    session: SessionDep,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    _no_store(response)
    return _sso_complete(
        request, session, "oidc", str(body.get("code", "")), str(body.get("state", ""))
    )
