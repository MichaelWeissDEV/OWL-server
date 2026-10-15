"""Is the server *open* (no authentication) or *secured*?

Out of the box the server is **open**: anyone who can reach it is an administrator - the
frictionless way to try it on localhost or inside a trusted network. It becomes secured when

1. the operator forces it (``OWL_SERVER_OPEN=false``), or
2. something to authenticate with is configured (admin token or an external identity provider), or
3. an administrator runs the *secure this server* step (dashboard or ``POST /setup/secure``), which
   creates the first administrator account and records ``secured = true`` in the database.

``OWL_SERVER_OPEN=true`` forces open mode again. Open mode is announced loudly (log, API, dashboard).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from owl_server import models as m
from owl_server.config import Settings

KEY = "secured"


def get_flag(session: Session, key: str) -> str | None:
    row = session.get(m.ServerSetting, key)
    return None if row is None else row.value


def set_flag(session: Session, key: str, value: str) -> None:
    row = session.get(m.ServerSetting, key)
    if row is None:
        session.add(m.ServerSetting(key=key, value=value))
    else:
        row.value = value
    session.flush()


def open_state(settings: Settings, session: Session) -> tuple[bool, str]:
    """``(is_open, reason)``; the reason says which rule decided."""
    if settings.open is not None:
        return settings.open, "forced by OWL_SERVER_OPEN"
    flag = get_flag(session, KEY)
    if flag is not None:
        return flag != "true", "set in the dashboard"
    if settings.admin_token or settings.external_providers:
        return False, "an admin token or identity provider is configured"
    return True, "default: nothing to authenticate with is configured yet"


def is_open(settings: Settings, session: Session) -> bool:
    return open_state(settings, session)[0]
