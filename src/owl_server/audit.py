"""Audit log. Never records secrets (tokens, passwords, Authorization headers)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from owl_server.models import AuditEvent
from owl_server.permissions import Principal


def record(
    session: Session,
    principal: Principal | str,
    action: str,
    target: str = "",
    detail: str = "",
    ip: str = "",
) -> None:
    actor = principal if isinstance(principal, str) else principal.actor
    session.add(
        AuditEvent(
            actor=actor[:200],
            action=action[:64],
            target=target[:300],
            detail=detail[:2000],
            ip=ip[:64],
        )
    )
