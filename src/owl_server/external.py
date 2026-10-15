"""Turning an external identity (OIDC, OAuth, LDAP, proxy) into an OWL account with rights."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from owl_server import accounts
from owl_server import models as m
from owl_server.config import Mapping


class ExternalLoginError(Exception):
    """Sign-in refused. ``public`` is safe to show; the HTTP layer decides the status code."""

    def __init__(self, public: str, status: int = 403) -> None:
        super().__init__(public)
        self.public = public
        self.status = status


def provision(
    session: Session,
    mapping: Mapping,
    *,
    provider: str,
    subject: str,
    username: str,
    email: str | None,
    groups: list[str],
    touch: bool = True,
) -> m.User:
    """Find or create the account for an external identity and synchronise its rights.

    - ``is_admin`` follows the groups **only when admin groups are configured** (otherwise an
      administrator can grant it in the dashboard without it being reset at the next login);
    - memberships are synchronised for the registries named in the group mapping; memberships
      of other registries are left alone (they can be managed in the dashboard).
    """
    user = session.scalar(
        select(m.User).where(m.User.provider == provider, m.User.subject == subject)
    )
    if user is None:
        existing = accounts.get_user(session, username)
        if existing is not None and existing.provider == "local":
            # a local account with the same name is never taken over by an external login
            username = f"{username}@{provider}"
            existing = accounts.get_user(session, username)
        if existing is not None and existing.provider == provider and existing.subject is None:
            user = existing  # pre-created by an administrator: link it on first login
            user.subject = subject
        elif not mapping.auto_create:
            raise ExternalLoginError(
                "This account is not allowed to sign in. Ask an administrator."
            )
        else:
            try:
                user = accounts.create_user(
                    session, username, None, email=email, provider=provider, subject=subject
                )
            except accounts.AccountError as exc:
                raise ExternalLoginError(str(exc), 409) from exc
    if not user.active:
        raise ExternalLoginError("This account is disabled.")
    if email and not user.email:
        user.email = email
    if mapping.admin_values:
        user.is_admin = any(g in mapping.admin_values for g in groups)
    for group in groups:
        for slug, role in mapping.registry_roles.get(group, {}).items():
            registry = session.scalar(select(m.Registry).where(m.Registry.slug == slug))
            if registry is not None:
                accounts.set_membership(session, registry, user, role)
    # a group that is no longer present removes the mapped membership again
    wanted = {
        (slug, role) for g in groups for slug, role in mapping.registry_roles.get(g, {}).items()
    }
    for group_roles in mapping.registry_roles.values():
        for slug in group_roles:
            registry = session.scalar(select(m.Registry).where(m.Registry.slug == slug))
            if registry is not None and not any(s == slug for s, _ in wanted):
                accounts.set_membership(session, registry, user, None)
    if touch:
        user.last_login = m.now()
    session.flush()
    return user
