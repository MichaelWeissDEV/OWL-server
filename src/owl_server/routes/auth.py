"""Login, sessions, personal tokens and (optional) OpenID Connect."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from owl_server import accounts, audit
from owl_server import models as m
from owl_server.deps import PrincipalDep, SessionDep, app_state, client_ip
from owl_server.oidc import OidcError
from owl_server.permissions import ROLES, is_server_admin

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
def auth_config(request: Request) -> dict[str, Any]:
    """What login methods this server offers (used by the dashboard's login page)."""
    settings = app_state(request).settings
    return {
        "local_accounts": settings.local_accounts,
        "oidc": settings.oidc is not None,
        "mode": settings.mode,
    }


@router.post("/login")
def login(
    request: Request,
    response: Response,
    session: SessionDep,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    settings = app_state(request).settings
    if not settings.local_accounts:
        raise HTTPException(404, "Local accounts are not enabled on this server")
    username, password = str(body.get("username", "")), str(body.get("password", ""))
    _limit(request, "login")
    _limit(request, f"login:{username.lower()}")
    user = accounts.authenticate_password(session, username, password)
    if user is None:
        audit.record(
            session, "anonymous", "auth.login_failed", username[:100], ip=client_ip(request)
        )
        session.commit()
        raise HTTPException(401, "Wrong username or password")
    audit.record(session, f"user:{user.username}", "auth.login", ip=client_ip(request))
    result = _session_response(session, request, user)
    session.commit()
    _no_store(response)
    return result


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


# -- OpenID Connect ------------------------------------------------------------------------------


def _oidc(request: Request):  # type: ignore[no-untyped-def]
    service = app_state(request).oidc
    if service is None:
        raise HTTPException(404, "OpenID Connect is not configured on this server")
    return service


@router.get("/oidc/login")
def oidc_login(
    request: Request, session: SessionDep, as_json: Annotated[bool, Query(alias="json")] = False
):  # type: ignore[no-untyped-def]
    """Start the login: redirect to the identity provider (or return the URL with ``?json=1``)."""
    _limit(request, "oidc")
    service = _oidc(request)
    try:
        url = service.begin(session)
    except OidcError as exc:
        raise HTTPException(502, exc.public) from exc
    session.commit()
    if as_json:
        return {"authorization_url": url}
    return RedirectResponse(url, status_code=302)


def _complete(request: Request, session: Session, code: str, state: str) -> dict[str, Any]:
    service = _oidc(request)
    settings = app_state(request).settings
    assert settings.oidc is not None
    try:
        claims = service.complete(session, code, state)
    except OidcError as exc:
        audit.record(
            session, "anonymous", "auth.oidc_failed", detail=str(exc)[:300], ip=client_ip(request)
        )
        session.commit()
        raise HTTPException(401 if "provider" not in exc.public else 502, exc.public) from exc
    username = str(claims.get(settings.oidc.username_claim) or claims.get("email") or claims["sub"])
    user = session.scalar(
        select(m.User).where(m.User.provider == "oidc", m.User.subject == str(claims["sub"]))
    )
    if user is None:
        if accounts.get_user(session, username) is not None:
            username = f"{username}@oidc"
        try:
            user = accounts.create_user(
                session,
                username,
                None,
                email=claims.get("email"),
                provider="oidc",
                subject=str(claims["sub"]),
            )
        except accounts.AccountError as exc:
            raise HTTPException(409, str(exc)) from exc
    if not user.active:
        raise HTTPException(403, "This account is disabled")
    values = service.claim_values(claims)
    user.is_admin = any(v in settings.oidc.admin_values for v in values)
    for value in values:
        for slug, role in settings.oidc.registry_roles.get(value, {}).items():
            registry = session.scalar(select(m.Registry).where(m.Registry.slug == slug))
            if registry is not None:
                accounts.set_membership(session, registry, user, role)
    user.last_login = m.now()
    audit.record(session, f"user:{user.username}", "auth.oidc_login", ip=client_ip(request))
    result = _session_response(session, request, user)
    session.commit()
    return result


@router.get("/oidc/callback")
def oidc_callback(
    request: Request, response: Response, session: SessionDep, code: str, state: str
) -> dict[str, Any]:
    _no_store(response)
    return _complete(request, session, code, state)


@router.post("/oidc/exchange")
def oidc_exchange(
    request: Request,
    response: Response,
    session: SessionDep,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """For single-page apps: the redirect lands in the dashboard, which posts ``code`` and ``state`` here."""
    _no_store(response)
    return _complete(request, session, str(body.get("code", "")), str(body.get("state", "")))
