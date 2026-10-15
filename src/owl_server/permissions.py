"""Principals and the role model: reader < publisher < admin, evaluated per registry."""

from __future__ import annotations

from dataclasses import dataclass

ROLES = ("reader", "publisher", "admin")
RANK = {role: i for i, role in enumerate(ROLES)}


def at_least(role: str | None, needed: str) -> bool:
    return role is not None and RANK[role] >= RANK[needed]


def lower(a: str | None, b: str | None) -> str | None:
    if a is None or b is None:
        return None
    return a if RANK[a] <= RANK[b] else b


@dataclass(frozen=True)
class Principal:
    """Who is calling. ``kind``: anonymous, bootstrap (env admin token), user or service."""

    kind: str = "anonymous"
    user_id: int | None = None
    username: str = "anonymous"
    is_admin: bool = False
    token_role: str | None = None  #: cap of the token used (None = no cap)
    token_registry_id: int | None = None  #: registry the token is limited to
    memberships: tuple[tuple[int, str], ...] = ()  #: (registry id, role) of the user

    @property
    def authenticated(self) -> bool:
        return self.kind != "anonymous"

    @property
    def actor(self) -> str:
        return f"{self.kind}:{self.username}"


ANONYMOUS = Principal()


def is_server_admin(principal: Principal) -> bool:
    """May manage registries, users and tokens (a capped or registry-scoped token may not)."""
    if principal.kind == "bootstrap":
        return True
    return (
        principal.kind == "user"
        and principal.is_admin
        and principal.token_role in (None, "admin")
        and principal.token_registry_id is None
    )


def effective_role(principal: Principal, registry_id: int, visibility: str) -> str | None:
    """The role *principal* has in the registry (``None`` = no access at all)."""
    role: str | None = None
    if principal.kind == "bootstrap":
        role = "admin"
    elif principal.kind == "user":
        role = "admin" if principal.is_admin else dict(principal.memberships).get(registry_id)
        if role is not None and principal.token_role is not None:
            role = lower(role, principal.token_role)
        if principal.token_registry_id not in (None, registry_id):
            role = None
    elif principal.kind == "service":
        # a service token grants exactly its own role, only inside its registry
        role = principal.token_role if principal.token_registry_id == registry_id else None
    if role is None and visibility == "public":
        role = "reader"
    return role
