"""LDAP / Active Directory sign-in: find the user with a service account, then bind as that user.

The password is only ever checked by the directory (a bind), never stored. Empty passwords are
refused (many servers treat an empty password as an anonymous bind that "succeeds").
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ldap3 import ALL, SAFE_SYNC, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

from owl_server.config import LdapSettings


class LdapError(Exception):
    """The directory could not be used (network, TLS, service account)."""


@dataclass
class LdapIdentity:
    dn: str
    username: str
    email: str | None
    groups: list[str]  #: group DNs as returned by the directory, plus their short names (CN)


def _short(dn: str) -> str:
    try:
        first = parse_dn(dn)[0]
        return first[1]
    except Exception:  # noqa: BLE001 - not a DN: use as is
        return dn


class LdapService:
    def __init__(
        self, settings: LdapSettings, connection_factory: Callable[..., Connection] | None = None
    ) -> None:
        self.settings = settings
        self._factory = connection_factory

    def _server(self) -> Server:
        s = self.settings
        tls = None
        if s.url.lower().startswith("ldaps://") or s.start_tls:
            tls = Tls(
                validate=ssl.CERT_REQUIRED if s.verify_tls else ssl.CERT_NONE,
                ca_certs_file=s.ca_file,
            )
        return Server(s.url, get_info=ALL, tls=tls, connect_timeout=s.timeout)

    def _connect(self, user: str, password: str) -> Connection:
        if self._factory is not None:
            return self._factory(user, password)
        conn = Connection(
            self._server(),
            user=user,
            password=password,
            client_strategy=SAFE_SYNC,
            receive_timeout=self.settings.timeout,
            raise_exceptions=False,
        )
        return conn

    def _bind(self, conn: Connection) -> bool:
        if self.settings.start_tls and self._factory is None:
            conn.open()
            conn.start_tls()
        result = conn.bind()
        return bool(result[0] if isinstance(result, tuple) else result)

    def authenticate(self, username: str, password: str) -> LdapIdentity | None:
        """The identity if the credentials are right, ``None`` if they are wrong.

        Raises :class:`LdapError` when the directory itself is unusable.
        """
        if not username or not password:
            return None  # never let an empty password reach the server
        s = self.settings
        try:
            service = self._connect(s.bind_dn, s.bind_password)
            if not self._bind(service):
                raise LdapError("the service account could not bind")
            flt = s.user_filter.replace("{username}", escape_filter_chars(username))
            attrs = [s.username_attr, s.email_attr, s.group_attr]
            found = service.search(s.user_base, flt, attributes=attrs, size_limit=2)
            if isinstance(found, tuple):  # SAFE_SYNC: (status, result, response, request)
                ok, response = found[0], found[2]
            else:  # other strategies (and the offline mock used in tests)
                ok, response = bool(found), service.response
            entries = [e for e in (response or []) if e.get("type") == "searchResEntry"]
            service.unbind()
            if not ok or len(entries) != 1:
                return None  # unknown user, or an ambiguous filter: refuse
            entry: dict[str, Any] = entries[0]
            attributes = entry.get("attributes", {})
            user_conn = self._connect(entry["dn"], password)
            if not self._bind(user_conn):
                return None
            user_conn.unbind()
        except LDAPException as exc:
            raise LdapError(f"directory error: {exc}") from exc
        except OSError as exc:
            raise LdapError(f"directory unreachable: {exc}") from exc

        def one(value: Any) -> str | None:
            if isinstance(value, list):
                value = value[0] if value else None
            return str(value) if value not in (None, "") else None

        raw_groups = attributes.get(s.group_attr) or []
        if not isinstance(raw_groups, list):
            raw_groups = [raw_groups]
        groups: list[str] = []
        for dn in map(str, raw_groups):
            groups.extend([dn, _short(dn)])
        return LdapIdentity(
            dn=str(entry["dn"]),
            username=one(attributes.get(s.username_attr)) or username,
            email=one(attributes.get(s.email_attr)),
            groups=groups,
        )
