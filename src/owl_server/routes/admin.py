"""Administration: users, service tokens and the audit log (server administrators only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from sqlalchemy import select

from owl_server import accounts, audit
from owl_server import models as m
from owl_server.deps import AdminDep, SessionDep, app_state, client_ip

router = APIRouter(prefix="/admin")


def _user_dict(user: m.User) -> dict[str, Any]:
    return {
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "active": user.active,
        "provider": user.provider,
        "created_at": user.created_at,
        "last_login": user.last_login,
    }


@router.get("/users")
def list_users(session: SessionDep, admin: AdminDep) -> list[dict[str, Any]]:
    return [_user_dict(u) for u in session.scalars(select(m.User).order_by(m.User.username))]


@router.post("/users", status_code=201)
def create_user(
    request: Request, session: SessionDep, admin: AdminDep, body: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    if not app_state(request).settings.local_accounts:
        raise HTTPException(404, "Local accounts are not enabled on this server")
    try:
        user = accounts.create_user(
            session,
            str(body.get("username", "")),
            str(body.get("password", "")),
            is_admin=bool(body.get("is_admin", False)),
            email=body.get("email"),
        )
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(
        session, admin, "user.create", user.username, f"admin={user.is_admin}", client_ip(request)
    )
    session.commit()
    return _user_dict(user)


@router.patch("/users/{username}")
def update_user(
    request: Request,
    session: SessionDep,
    admin: AdminDep,
    username: str,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    user = accounts.get_user(session, username)
    if user is None:
        raise HTTPException(404, "User not found")
    changed = []
    if "active" in body:
        user.active = bool(body["active"])
        changed.append(f"active={user.active}")
        if not user.active:
            accounts.revoke_sessions(session, user.id)
    if "is_admin" in body:
        if admin.kind == "user" and admin.user_id == user.id and not body["is_admin"]:
            raise HTTPException(409, "You cannot remove your own administrator rights")
        user.is_admin = bool(body["is_admin"])
        changed.append(f"is_admin={user.is_admin}")
    if "password" in body:
        if user.provider != "local":
            raise HTTPException(422, "This account is managed by the identity provider")
        from owl_server import security

        try:
            user.password_hash = security.hash_password(str(body["password"]))
        except security.WeakPassword as exc:
            raise HTTPException(422, str(exc)) from exc
        accounts.revoke_sessions(session, user.id)
        changed.append("password")
    audit.record(session, admin, "user.update", username, ",".join(changed), client_ip(request))
    session.commit()
    return _user_dict(user)


@router.get("/tokens")
def list_tokens(session: SessionDep, admin: AdminDep) -> list[dict[str, Any]]:
    registries = {r.id: r.slug for r in session.scalars(select(m.Registry))}
    users = {u.id: u.username for u in session.scalars(select(m.User))}
    rows = session.scalars(
        select(m.ApiToken).where(m.ApiToken.kind == "api").order_by(m.ApiToken.id)
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "prefix": r.prefix,
            "role": r.role,
            "registry": registries.get(r.registry_id) if r.registry_id else None,
            "user": users.get(r.user_id) if r.user_id else None,
            "created_at": r.created_at,
            "expires_at": r.expires_at,
            "revoked_at": r.revoked_at,
            "last_used_at": r.last_used_at,
        }
        for r in rows
    ]


@router.post("/tokens", status_code=201)
def create_service_token(
    request: Request, session: SessionDep, admin: AdminDep, body: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    """A token without a user, limited to one registry - for CI jobs and automation."""
    slug = str(body.get("registry", ""))
    registry = session.scalar(select(m.Registry).where(m.Registry.slug == slug))
    if registry is None:
        raise HTTPException(404, "Registry not found")
    ttl = body.get("ttl_hours")
    try:
        secret, row = accounts.create_token(
            session,
            name=str(body.get("name", "service token")),
            role=str(body.get("role", "reader")),
            registry=registry,
            ttl_hours=float(ttl) if ttl else None,
        )
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(
        session,
        admin,
        "token.create",
        row.prefix,
        f"service registry={slug} role={row.role}",
        client_ip(request),
    )
    session.commit()
    return {
        "token": secret,
        "id": row.id,
        "prefix": row.prefix,
        "role": row.role,
        "registry": slug,
        "expires_at": row.expires_at,
    }


@router.delete("/tokens/{token_id}")
def revoke(
    request: Request, session: SessionDep, admin: AdminDep, token_id: int
) -> dict[str, bool]:
    row = session.get(m.ApiToken, token_id)
    if row is None or not accounts.revoke_token(session, token_id):
        raise HTTPException(404, "Token not found or already revoked")
    audit.record(session, admin, "token.revoke", row.prefix, ip=client_ip(request))
    session.commit()
    return {"revoked": True}


@router.get("/audit")
def audit_log(
    session: SessionDep,
    admin: AdminDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    action: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(m.AuditEvent).order_by(m.AuditEvent.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(m.AuditEvent.action.startswith(action))
    return [
        {
            "id": e.id,
            "at": e.at,
            "actor": e.actor,
            "action": e.action,
            "target": e.target,
            "detail": e.detail,
            "ip": e.ip,
        }
        for e in session.scalars(stmt)
    ]
