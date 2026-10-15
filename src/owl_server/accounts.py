"""Users, memberships, API tokens and login sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from owl_server import models as m
from owl_server import security
from owl_server.permissions import RANK, ROLES, Principal

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-@")


class AccountError(ValueError):
    """An invalid or conflicting account operation (message is safe to show)."""


def _check_username(name: str) -> str:
    name = name.strip()
    if not 2 <= len(name) <= 100 or not set(name) <= USERNAME_CHARS:
        raise AccountError("Usernames have 2-100 characters: letters, digits and . _ - @")
    return name


def create_user(
    session: Session,
    username: str,
    password: str | None,
    *,
    is_admin: bool = False,
    email: str | None = None,
    provider: str = "local",
    subject: str | None = None,
) -> m.User:
    username = _check_username(username)
    if session.scalar(select(m.User).where(m.User.username == username)):
        raise AccountError(f"The user '{username}' already exists")
    try:
        hashed = security.hash_password(password) if password is not None else None
    except security.WeakPassword as exc:
        raise AccountError(str(exc)) from exc
    user = m.User(
        username=username,
        email=email,
        password_hash=hashed,
        is_admin=is_admin,
        provider=provider,
        subject=subject,
    )
    session.add(user)
    session.flush()
    return user


def get_user(session: Session, username: str) -> m.User | None:
    return session.scalar(select(m.User).where(m.User.username == username))


def authenticate_password(session: Session, username: str, password: str) -> m.User | None:
    """Check a local login. Always does the same amount of work, whether the user exists or not."""
    user = get_user(session, username)
    hashed = user.password_hash if user and user.active and user.provider == "local" else None
    if not security.verify_password(password, hashed) or user is None:
        return None
    if hashed and security.needs_rehash(hashed):
        user.password_hash = security.hash_password(password)
    user.last_login = m.now()
    return user


def change_password(session: Session, user: m.User, old: str, new: str) -> None:
    if user.provider != "local" or not security.verify_password(old, user.password_hash):
        raise AccountError("The current password is wrong")
    try:
        user.password_hash = security.hash_password(new)
    except security.WeakPassword as exc:
        raise AccountError(str(exc)) from exc
    revoke_sessions(session, user.id)  # a password change logs every session out


def set_membership(session: Session, registry: m.Registry, user: m.User, role: str | None) -> None:
    if role is not None and role not in ROLES:
        raise AccountError(f"Role must be one of: {', '.join(ROLES)}")
    row = session.get(m.Membership, (registry.id, user.id))
    if role is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(m.Membership(registry_id=registry.id, user_id=user.id, role=role))
    else:
        row.role = role
    session.flush()


def memberships_of(session: Session, user_id: int) -> tuple[tuple[int, str], ...]:
    rows = session.execute(
        select(m.Membership.registry_id, m.Membership.role).where(m.Membership.user_id == user_id)
    ).all()
    return tuple((int(r), str(role)) for r, role in rows)


def create_token(
    session: Session,
    *,
    name: str,
    role: str,
    user: m.User | None = None,
    registry: m.Registry | None = None,
    kind: str = "api",
    ttl_hours: float | None = None,
) -> tuple[str, m.ApiToken]:
    """Create a token and return ``(secret, row)``. The secret cannot be recovered later."""
    if role not in ROLES:
        raise AccountError(f"Role must be one of: {', '.join(ROLES)}")
    if user is None and registry is None and role != "reader":
        raise AccountError("A token without a user must be limited to one registry")
    secret, prefix, digest = security.new_token()
    expires = (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat() if ttl_hours else None
    row = m.ApiToken(
        kind=kind,
        name=name[:100],
        prefix=prefix,
        token_hash=digest,
        user_id=user.id if user else None,
        role=role,
        registry_id=registry.id if registry else None,
        expires_at=expires,
    )
    session.add(row)
    session.flush()
    return secret, row


def revoke_token(session: Session, token_id: int) -> bool:
    row = session.get(m.ApiToken, token_id)
    if row is None or row.revoked_at:
        return False
    row.revoked_at = m.now()
    return True


def revoke_sessions(session: Session, user_id: int) -> None:
    for row in session.scalars(
        select(m.ApiToken).where(
            m.ApiToken.user_id == user_id,
            m.ApiToken.kind == "session",
            m.ApiToken.revoked_at.is_(None),
        )
    ):
        row.revoked_at = m.now()


def principal_for_token(session: Session, secret: str) -> Principal | None:
    """Resolve a bearer secret to a principal; ``None`` for unknown/revoked/expired tokens."""
    row = session.scalar(
        select(m.ApiToken).where(m.ApiToken.token_hash == security.hash_token(secret))
    )
    if row is None or row.revoked_at:
        return None
    if row.expires_at and datetime.fromisoformat(row.expires_at) <= datetime.now(UTC):
        return None
    row.last_used_at = m.now()
    if row.user_id is None:
        return Principal(
            kind="service",
            username=f"token:{row.prefix}",
            token_role=row.role,
            token_registry_id=row.registry_id,
        )
    user = session.get(m.User, row.user_id)
    if user is None or not user.active:
        return None
    return Principal(
        kind="user",
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        token_role=None if row.kind == "session" else row.role,
        token_registry_id=row.registry_id,
        memberships=memberships_of(session, user.id),
    )


__all__ = [
    "RANK",
    "AccountError",
    "authenticate_password",
    "change_password",
    "create_token",
    "create_user",
    "get_user",
    "principal_for_token",
    "revoke_sessions",
    "revoke_token",
    "set_membership",
]
