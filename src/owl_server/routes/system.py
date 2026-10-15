"""Health, readiness and registry management."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from owl_server import __version__, access, accounts, audit, db
from owl_server import models as m
from owl_server.deps import (
    AdminDep,
    PrincipalDep,
    SessionDep,
    app_state,
    client_ip,
    effective_visibility,
    load_registry,
)
from owl_server.permissions import effective_role, is_server_admin

router = APIRouter()
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Always open (for load balancers)."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request, session: SessionDep) -> JSONResponse:
    """Readiness: the database answers and the schema is at the newest migration."""
    state = app_state(request)
    try:
        session.execute(text("select 1"))
        current = db.current_revision(session.get_bind())  # type: ignore[arg-type]
        head = db.head_revision(state.settings.database_url)
    except Exception:  # noqa: BLE001 - report "not ready" rather than a stack trace
        return JSONResponse(
            {"status": "not ready", "reason": "database unreachable"}, status_code=503
        )
    if current != head:
        return JSONResponse(
            {
                "status": "not ready",
                "reason": "migrations pending",
                "revision": current,
                "head": head,
            },
            status_code=503,
        )
    return JSONResponse({"status": "ready", "revision": current, "version": __version__})


def _registry_dict(session, settings, registry: m.Registry, role: str | None) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    count = session.scalar(
        select(func.count())
        .select_from(m.Skill)
        .where(m.Skill.registry_id == registry.id, m.Skill.current_version_id.is_not(None))
    )
    return {
        "slug": registry.slug,
        "name": registry.name,
        "description": registry.description,
        "visibility": effective_visibility(settings, registry),
        "skills": int(count or 0),
        "role": role,
        "created_at": registry.created_at,
    }


@router.get("/registries")
def list_registries(
    request: Request, session: SessionDep, principal: PrincipalDep
) -> list[dict[str, Any]]:
    """The registries the caller may see (private ones only with access)."""
    settings = app_state(request).settings
    out = []
    for registry in session.scalars(select(m.Registry).order_by(m.Registry.slug)):
        role = effective_role(principal, registry.id, effective_visibility(settings, registry))
        if role is not None:
            out.append(_registry_dict(session, settings, registry, role))
    return out


def _check_visibility(settings, visibility: str) -> None:  # type: ignore[no-untyped-def]
    if visibility not in ("public", "private"):
        raise HTTPException(422, "visibility must be public or private")
    if settings.mode == "public" and visibility != "public":
        raise HTTPException(422, "This server runs in public mode: all registries are public")
    if settings.mode == "private" and visibility != "private":
        raise HTTPException(422, "This server runs in private mode: all registries are private")


@router.post("/registries", status_code=201)
def create_registry(
    request: Request, session: SessionDep, admin: AdminDep, body: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    settings = app_state(request).settings
    slug = str(body.get("slug", "")).strip()
    if not SLUG_RE.fullmatch(slug) or len(slug) > 64:
        raise HTTPException(422, "slug: lower-case letters, digits and single hyphens (max 64)")
    visibility = str(body.get("visibility", "private"))
    _check_visibility(settings, visibility)
    if session.scalar(select(m.Registry).where(m.Registry.slug == slug)):
        raise HTTPException(409, "A registry with this slug already exists")
    registry = m.Registry(
        slug=slug,
        name=str(body.get("name") or slug)[:200],
        description=str(body.get("description", "")),
        visibility=visibility,
    )
    session.add(registry)
    session.flush()
    audit.record(
        session, admin, "registry.create", slug, f"visibility={visibility}", client_ip(request)
    )
    session.commit()
    return _registry_dict(session, settings, registry, "admin")


@router.get("/registries/{slug}")
def get_registry(
    request: Request, session: SessionDep, principal: PrincipalDep, slug: str
) -> dict[str, Any]:
    settings = app_state(request).settings
    ctx = load_registry(session, settings, principal, slug)
    return _registry_dict(session, settings, ctx.registry, ctx.role)


@router.patch("/registries/{slug}")
def update_registry(
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    slug: str,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    settings = app_state(request).settings
    ctx = load_registry(session, settings, principal, slug)
    ctx.require("admin")
    registry = ctx.registry
    if "visibility" in body:
        if not is_server_admin(principal):
            raise HTTPException(403, "Only a server administrator may change the visibility")
        _check_visibility(settings, str(body["visibility"]))
        registry.visibility = str(body["visibility"])
    if "name" in body:
        registry.name = str(body["name"])[:200]
    if "description" in body:
        registry.description = str(body["description"])
    audit.record(
        session, principal, "registry.update", slug, ",".join(sorted(body)), client_ip(request)
    )
    session.commit()
    return _registry_dict(session, settings, registry, ctx.role)


@router.delete("/registries/{slug}")
def delete_registry(
    request: Request, session: SessionDep, admin: AdminDep, slug: str, force: bool = False
) -> dict[str, bool]:
    registry = session.scalar(select(m.Registry).where(m.Registry.slug == slug))
    if registry is None:
        raise HTTPException(404, "Registry not found")
    if slug == app_state(request).settings.default_registry:
        raise HTTPException(409, "The default registry cannot be deleted")
    skills = session.scalars(select(m.Skill).where(m.Skill.registry_id == registry.id)).all()
    if skills and not force:
        raise HTTPException(
            409, f"The registry still contains {len(skills)} skills; use ?force=true"
        )
    from owl_server.repository import SkillRepository

    repo = SkillRepository(session, registry)
    for skill in skills:
        repo.delete(skill.author, skill.name)
    for table in (m.Collection,):
        for row in session.scalars(select(table).where(table.registry_id == registry.id)):
            repo.collection_delete(row.name)
    for membership in session.scalars(
        select(m.Membership).where(m.Membership.registry_id == registry.id)
    ):
        session.delete(membership)
    for token in session.scalars(select(m.ApiToken).where(m.ApiToken.registry_id == registry.id)):
        token.revoked_at = m.now()
        token.registry_id = None
    session.flush()
    session.delete(registry)
    audit.record(
        session, admin, "registry.delete", slug, f"skills={len(skills)}", client_ip(request)
    )
    session.commit()
    return {"deleted": True}


# -- members --------------------------------------------------------------------------------


@router.get("/registries/{slug}/members")
def list_members(
    request: Request, session: SessionDep, principal: PrincipalDep, slug: str
) -> list[dict[str, str]]:
    ctx = load_registry(session, app_state(request).settings, principal, slug)
    ctx.require("admin")
    rows = session.execute(
        select(m.User.username, m.Membership.role)
        .join(m.Membership, m.Membership.user_id == m.User.id)
        .where(m.Membership.registry_id == ctx.registry.id)
        .order_by(m.User.username)
    ).all()
    return [{"username": u, "role": r} for u, r in rows]


@router.put("/registries/{slug}/members/{username}")
def set_member(
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    slug: str,
    username: str,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, str]:
    ctx = load_registry(session, app_state(request).settings, principal, slug)
    ctx.require("admin")
    user = accounts.get_user(session, username)
    if user is None:
        raise HTTPException(404, "User not found")
    try:
        accounts.set_membership(session, ctx.registry, user, str(body.get("role", "")))
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(
        session,
        principal,
        "member.set",
        f"{slug}:{username}",
        f"role={body.get('role')}",
        client_ip(request),
    )
    session.commit()
    return {"username": username, "role": str(body.get("role"))}


@router.delete("/registries/{slug}/members/{username}")
def remove_member(
    request: Request, session: SessionDep, principal: PrincipalDep, slug: str, username: str
) -> dict[str, bool]:
    ctx = load_registry(session, app_state(request).settings, principal, slug)
    ctx.require("admin")
    user = accounts.get_user(session, username)
    if user is None:
        raise HTTPException(404, "User not found")
    accounts.set_membership(session, ctx.registry, user, None)
    audit.record(session, principal, "member.remove", f"{slug}:{username}", ip=client_ip(request))
    session.commit()
    return {"removed": True}


# -- first-run setup: from "open" to "secured" --------------------------------------------------


def _provider_summary(settings) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "local_accounts": settings.local_accounts,
        "oidc": settings.oidc is not None,
        "oauth": settings.oauth is not None,
        "ldap": settings.ldap is not None,
        "proxy": settings.proxy is not None,
        "admin_token": settings.admin_token is not None,
    }


@router.get("/setup/status")
def setup_status(request: Request, session: SessionDep) -> dict[str, Any]:
    """Open to everyone: is the server open, and what is configured? (No secrets.)"""
    settings = app_state(request).settings
    is_open, reason = access.open_state(settings, session)
    users = session.scalar(select(func.count()).select_from(m.User)) or 0
    admins = (
        session.scalar(select(func.count()).select_from(m.User).where(m.User.is_admin.is_(True)))
        or 0
    )
    return {
        "open": is_open,
        "reason": reason,
        "users": int(users),
        "admins": int(admins),
        "providers": _provider_summary(settings),
        "version": __version__,
    }


@router.post("/setup/secure", status_code=201)
def secure_server(
    request: Request, session: SessionDep, body: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    """Turn an open server into a secured one: creates the first administrator and requires
    authentication from now on. Only possible while the server is open."""
    state = app_state(request)
    settings = state.settings
    if settings.open is True:
        raise HTTPException(
            409, "OWL_SERVER_OPEN=true forces open mode; remove it to secure the server"
        )
    if not access.is_open(settings, session):
        raise HTTPException(409, "This server is already secured")
    if not settings.local_accounts:
        raise HTTPException(
            409, "Local accounts are disabled; configure an identity provider instead"
        )
    try:
        user = accounts.create_user(
            session, str(body.get("username", "")), str(body.get("password", "")), is_admin=True
        )
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc
    access.set_flag(session, access.KEY, "true")
    audit.record(session, "open:open-mode", "server.secured", user.username, ip=client_ip(request))
    secret, row = accounts.create_token(
        session,
        name="login session",
        role="reader",
        user=user,
        kind="session",
        ttl_hours=settings.session_ttl_hours,
    )
    session.commit()
    return {
        "token": secret,
        "expires_at": row.expires_at,
        "user": {"username": user.username, "is_admin": True},
    }
