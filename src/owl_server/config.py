"""Configuration from environment variables (``OWL_SERVER_*``), with Docker-secret support.

Every variable ``X`` can also be given as ``X_FILE`` pointing at a file whose content is the value,
which keeps secrets out of the process environment and of ``docker inspect``.

The server starts **open** (no authentication, everyone is an administrator) unless something to
authenticate with is configured or the operator secures it - see :mod:`owl_server.access`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PREFIX = "OWL_SERVER_"
MODES = ("public", "private", "mixed")


class ConfigError(Exception):
    """The configuration is invalid; the message says what to fix."""


def _get(name: str, default: str | None = None, env: dict[str, str] | None = None) -> str | None:
    source = env if env is not None else os.environ
    value = source.get(PREFIX + name)
    file_ref = source.get(PREFIX + name + "_FILE")
    if file_ref and not value:
        try:
            value = Path(file_ref).read_text("utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"{PREFIX}{name}_FILE: cannot read {file_ref}: {exc}") from exc
    return value if value not in (None, "") else default


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


#: Every switch that weakens security has a deliberately long name and is off by default. Anyone who
#: sets one makes a conscious decision; each active flag is logged as a warning at start-up.
INSECURE_FLAGS = {
    "ALLOW_INSECURE_OIDC_OVER_HTTP": "OIDC issuer is not https:// (tokens and codes travel unencrypted)",
    "ALLOW_INSECURE_OAUTH_OVER_HTTP": "OAuth endpoints are not https:// (codes and tokens travel unencrypted)",
    "ALLOW_INSECURE_LDAP_WITHOUT_TLS": "plain ldap:// without StartTLS (passwords travel unencrypted)",
    "ALLOW_INSECURE_DISABLE_OIDC_TLS_VERIFICATION": "OIDC server certificate is NOT verified",
    "ALLOW_INSECURE_DISABLE_OAUTH_TLS_VERIFICATION": "OAuth server certificate is NOT verified",
    "ALLOW_INSECURE_DISABLE_LDAP_TLS_VERIFICATION": "LDAP server certificate is NOT verified",
}


def _insecure(name: str, env: dict[str, str] | None) -> bool:
    """True when the long ``OWL_SERVER_<name>`` flag is set (see :data:`INSECURE_FLAGS`)."""
    return _bool(_get(name, env=env), False)


def active_insecure_flags(env: dict[str, str] | None = None) -> list[str]:
    return [f"{PREFIX}{n}: {why}" for n, why in INSECURE_FLAGS.items() if _insecure(n, env)]


def _verify(provider: str, env: dict[str, str] | None) -> bool:
    """TLS verification is always on; switching it off needs the long flag."""
    if _insecure(f"ALLOW_INSECURE_DISABLE_{provider}_TLS_VERIFICATION", env):
        return False
    if not _bool(_get(f"{provider}_VERIFY_TLS", env=env), True):
        raise ConfigError(
            f"{PREFIX}{provider}_VERIFY_TLS is no longer a switch. To turn certificate checking off "
            f"(never do this in production) set {PREFIX}ALLOW_INSECURE_DISABLE_{provider}_TLS_VERIFICATION=true"
        )
    return True


def _list(value: str | None, sep: str = ",") -> list[str]:
    return [v.strip() for v in (value or "").split(sep) if v.strip()]


@dataclass
class Mapping:
    """How an external identity becomes OWL rights (shared by every external provider)."""

    #: values of the groups/roles that make a user a **server admin** (empty: admin flag untouched)
    admin_values: list[str] = field(default_factory=list)
    #: group value -> {registry slug: role}; applied on every login
    registry_roles: dict[str, dict[str, str]] = field(default_factory=dict)
    #: create an account on first login (False: only pre-created users may sign in)
    auto_create: bool = True


@dataclass
class OidcSettings:
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scopes: str = "openid profile email"
    audience: str | None = None  #: defaults to the client id
    username_claim: str = "preferred_username"
    role_claim: str | None = None
    verify_tls: bool = True
    label: str = "Single sign-on"
    mapping: Mapping = field(default_factory=Mapping)

    @property
    def admin_values(self) -> list[str]:
        return self.mapping.admin_values

    @property
    def registry_roles(self) -> dict[str, dict[str, str]]:
        return self.mapping.registry_roles


@dataclass
class OAuthSettings:
    """Plain OAuth 2.0 (providers without OpenID Connect, e.g. GitHub)."""

    client_id: str
    client_secret: str | None
    redirect_uri: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: str = ""
    id_field: str = "id"
    username_field: str = "login"
    email_field: str = "email"
    groups_field: str | None = None
    allowed_users: list[str] = field(
        default_factory=list
    )  #: empty = anyone the provider authenticates
    label: str = "OAuth login"
    verify_tls: bool = True
    mapping: Mapping = field(default_factory=Mapping)


@dataclass
class LdapSettings:
    """LDAP / Active Directory: search the user with a service account, then bind as the user."""

    url: str
    bind_dn: str
    bind_password: str
    user_base: str
    user_filter: str = "(sAMAccountName={username})"  #: OpenLDAP: (uid={username})
    username_attr: str = "sAMAccountName"
    email_attr: str = "mail"
    group_attr: str = "memberOf"
    start_tls: bool = False
    verify_tls: bool = True
    ca_file: str | None = None
    timeout: int = 8
    label: str = "Directory login"
    mapping: Mapping = field(default_factory=Mapping)


@dataclass
class ProxySettings:
    """Authentication done by a reverse proxy in front of OWL (Kerberos/SPNEGO, SAML, oauth2-proxy,
    Authelia, ...). OWL trusts the headers **only** when they come with the shared secret."""

    secret: str
    user_header: str = "X-Remote-User"
    email_header: str = "X-Remote-Email"
    groups_header: str = "X-Remote-Groups"
    groups_separator: str = ","
    secret_header: str = "X-OWL-Proxy-Secret"
    mapping: Mapping = field(default_factory=Mapping)


@dataclass
class Settings:
    database_url: str
    mode: str = "mixed"
    default_registry: str = "default"
    admin_token: str | None = None
    #: True/False force open/secured; None = automatic (see owl_server.access)
    open: bool | None = None
    local_accounts: bool = True
    auto_migrate: bool = True
    max_body_mb: int = 40
    session_ttl_hours: int = 12
    cors_origins: list[str] = field(default_factory=list)
    login_rate_per_minute: int = 10
    public_url: str | None = None
    oidc: OidcSettings | None = None
    oauth: OAuthSettings | None = None
    ldap: LdapSettings | None = None
    proxy: ProxySettings | None = None

    @property
    def max_body_bytes(self) -> int:
        return self.max_body_mb * 1024 * 1024

    @property
    def external_providers(self) -> list[str]:
        return [
            n
            for n, v in (
                ("oidc", self.oidc),
                ("oauth", self.oauth),
                ("ldap", self.ldap),
                ("proxy", self.proxy),
            )
            if v is not None
        ]


def _mapping(prefix: str, env: dict[str, str] | None) -> Mapping:
    try:
        roles = json.loads(_get(f"{prefix}_REGISTRY_ROLES", "{}", env) or "{}")
    except ValueError as exc:
        raise ConfigError(f"{PREFIX}{prefix}_REGISTRY_ROLES is not valid JSON: {exc}") from exc
    if not isinstance(roles, dict):
        raise ConfigError(f"{PREFIX}{prefix}_REGISTRY_ROLES must be a JSON object")
    for group, regs in roles.items():
        if not isinstance(regs, dict) or any(
            r not in ("reader", "publisher", "admin") for r in regs.values()
        ):
            raise ConfigError(
                f"{PREFIX}{prefix}_REGISTRY_ROLES['{group}'] must map registry slugs to reader/publisher/admin"
            )
    return Mapping(
        admin_values=_list(_get(f"{prefix}_ADMIN_VALUES", env=env)),
        registry_roles=roles,
        auto_create=_bool(_get(f"{prefix}_AUTO_CREATE", env=env), True),
    )


GITHUB = {
    "authorize_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "userinfo_url": "https://api.github.com/user",
    "scopes": "read:user user:email",
    "username_field": "login",
    "label": "Sign in with GitHub",
}


def _oidc(env: dict[str, str] | None) -> OidcSettings | None:
    issuer = _get("OIDC_ISSUER", env=env)
    if not issuer:
        return None
    client_id, redirect = _get("OIDC_CLIENT_ID", env=env), _get("OIDC_REDIRECT_URI", env=env)
    if not client_id or not redirect:
        raise ConfigError("OIDC needs OWL_SERVER_OIDC_CLIENT_ID and OWL_SERVER_OIDC_REDIRECT_URI")
    if not issuer.startswith("https://") and not _insecure("ALLOW_INSECURE_OIDC_OVER_HTTP", env):
        raise ConfigError(
            "OWL_SERVER_OIDC_ISSUER must be an https:// URL "
            "(lab only: OWL_SERVER_ALLOW_INSECURE_OIDC_OVER_HTTP=true)"
        )
    return OidcSettings(
        issuer=issuer.rstrip("/"),
        client_id=client_id,
        client_secret=_get("OIDC_CLIENT_SECRET", env=env),
        redirect_uri=redirect,
        scopes=_get("OIDC_SCOPES", "openid profile email", env) or "openid",
        audience=_get("OIDC_AUDIENCE", env=env),
        username_claim=_get("OIDC_USERNAME_CLAIM", "preferred_username", env)
        or "preferred_username",
        role_claim=_get("OIDC_ROLE_CLAIM", env=env),
        verify_tls=_verify("OIDC", env),
        label=_get("OIDC_LABEL", "Single sign-on", env) or "Single sign-on",
        mapping=_mapping("OIDC", env),
    )


def _oauth(env: dict[str, str] | None) -> OAuthSettings | None:
    client_id = _get("OAUTH_CLIENT_ID", env=env)
    if not client_id:
        return None
    preset = (_get("OAUTH_PRESET", env=env) or "").lower()
    if preset not in ("", "github"):
        raise ConfigError("OWL_SERVER_OAUTH_PRESET must be empty or 'github'")
    base = dict(GITHUB) if preset == "github" else {}

    def pick(name: str, key: str, default: str | None = None) -> str:
        value = _get(f"OAUTH_{name}", env=env) or base.get(key) or default
        if not value:
            raise ConfigError(
                f"OAuth needs OWL_SERVER_OAUTH_{name} (or OWL_SERVER_OAUTH_PRESET=github)"
            )
        return value

    redirect = _get("OAUTH_REDIRECT_URI", env=env)
    if not redirect:
        raise ConfigError("OAuth needs OWL_SERVER_OAUTH_REDIRECT_URI")
    urls = [
        pick("AUTHORIZE_URL", "authorize_url"),
        pick("TOKEN_URL", "token_url"),
        pick("USERINFO_URL", "userinfo_url"),
    ]
    if any(not u.startswith("https://") for u in urls) and not _insecure(
        "ALLOW_INSECURE_OAUTH_OVER_HTTP", env
    ):
        raise ConfigError(
            "OAuth endpoints must be https:// URLs "
            "(lab only: OWL_SERVER_ALLOW_INSECURE_OAUTH_OVER_HTTP=true)"
        )
    return OAuthSettings(
        client_id=client_id,
        client_secret=_get("OAUTH_CLIENT_SECRET", env=env),
        redirect_uri=redirect,
        authorize_url=urls[0],
        token_url=urls[1],
        userinfo_url=urls[2],
        scopes=_get("OAUTH_SCOPES", base.get("scopes", ""), env) or "",
        id_field=_get("OAUTH_ID_FIELD", "id", env) or "id",
        username_field=_get("OAUTH_USERNAME_FIELD", base.get("username_field", "login"), env)
        or "login",
        email_field=_get("OAUTH_EMAIL_FIELD", "email", env) or "email",
        groups_field=_get("OAUTH_GROUPS_FIELD", env=env),
        allowed_users=_list(_get("OAUTH_ALLOWED_USERS", env=env)),
        label=_get("OAUTH_LABEL", base.get("label", "OAuth login"), env) or "OAuth login",
        verify_tls=_verify("OAUTH", env),
        mapping=_mapping("OAUTH", env),
    )


def _ldap(env: dict[str, str] | None) -> LdapSettings | None:
    url = _get("LDAP_URL", env=env)
    if not url:
        return None
    if not url.lower().startswith(("ldaps://", "ldap://")):
        raise ConfigError("OWL_SERVER_LDAP_URL must start with ldaps:// or ldap://")
    insecure_ok = _insecure("ALLOW_INSECURE_LDAP_WITHOUT_TLS", env)
    start_tls = _bool(_get("LDAP_START_TLS", env=env), False)
    if url.lower().startswith("ldap://") and not start_tls and not insecure_ok:
        raise ConfigError(
            "Plain ldap:// would send passwords unencrypted: use ldaps://, "
            "OWL_SERVER_LDAP_START_TLS=true, or OWL_SERVER_ALLOW_INSECURE_LDAP_WITHOUT_TLS=true for a lab"
        )
    missing = [
        n for n in ("BIND_DN", "BIND_PASSWORD", "USER_BASE") if not _get(f"LDAP_{n}", env=env)
    ]
    if missing:
        raise ConfigError("LDAP needs " + ", ".join(f"OWL_SERVER_LDAP_{n}" for n in missing))
    user_filter = _get("LDAP_USER_FILTER", "(sAMAccountName={username})", env) or ""
    if "{username}" not in user_filter:
        raise ConfigError("OWL_SERVER_LDAP_USER_FILTER must contain {username}")
    return LdapSettings(
        url=url,
        bind_dn=_get("LDAP_BIND_DN", env=env) or "",
        bind_password=_get("LDAP_BIND_PASSWORD", env=env) or "",
        user_base=_get("LDAP_USER_BASE", env=env) or "",
        user_filter=user_filter,
        username_attr=_get("LDAP_USERNAME_ATTR", "sAMAccountName", env) or "sAMAccountName",
        email_attr=_get("LDAP_EMAIL_ATTR", "mail", env) or "mail",
        group_attr=_get("LDAP_GROUP_ATTR", "memberOf", env) or "memberOf",
        start_tls=start_tls,
        verify_tls=_verify("LDAP", env),
        ca_file=_get("LDAP_CA_FILE", env=env),
        timeout=int(_get("LDAP_TIMEOUT", "8", env) or 8),
        label=_get("LDAP_LABEL", "Directory login", env) or "Directory login",
        mapping=_mapping("LDAP", env),
    )


def _proxy(env: dict[str, str] | None) -> ProxySettings | None:
    if not _bool(_get("PROXY_AUTH", env=env), False):
        return None
    secret = _get("PROXY_SECRET", env=env)
    if not secret or len(secret) < 24:
        raise ConfigError(
            "Proxy authentication needs OWL_SERVER_PROXY_SECRET (>= 24 characters): the proxy "
            "must send it so that OWL can tell real proxy headers from forged ones"
        )
    return ProxySettings(
        secret=secret,
        user_header=_get("PROXY_USER_HEADER", "X-Remote-User", env) or "X-Remote-User",
        email_header=_get("PROXY_EMAIL_HEADER", "X-Remote-Email", env) or "X-Remote-Email",
        groups_header=_get("PROXY_GROUPS_HEADER", "X-Remote-Groups", env) or "X-Remote-Groups",
        groups_separator=_get("PROXY_GROUPS_SEPARATOR", ",", env) or ",",
        secret_header=_get("PROXY_SECRET_HEADER", "X-OWL-Proxy-Secret", env)
        or "X-OWL-Proxy-Secret",
        mapping=_mapping("PROXY", env),
    )


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Read and validate the configuration. Raises :class:`ConfigError`."""
    database_url = _get("DATABASE_URL", env=env)
    if not database_url:
        raise ConfigError("OWL_SERVER_DATABASE_URL is required (e.g. postgresql://user:pw@db/owl)")
    mode = (_get("MODE", "mixed", env) or "mixed").lower()
    if mode not in MODES:
        raise ConfigError(f"OWL_SERVER_MODE must be one of {', '.join(MODES)}")
    admin_token = _get("ADMIN_TOKEN", env=env)
    if admin_token is not None and len(admin_token) < 24:
        raise ConfigError(
            "OWL_SERVER_ADMIN_TOKEN must be at least 24 characters (use a random value)"
        )
    max_body = int(_get("MAX_BODY_MB", "40", env) or 40)
    if max_body < 1:
        raise ConfigError("OWL_SERVER_MAX_BODY_MB must be at least 1")
    open_raw = _get("OPEN", env=env)
    return Settings(
        database_url=database_url,
        mode=mode,
        default_registry=_get("DEFAULT_REGISTRY", "default", env) or "default",
        admin_token=admin_token,
        open=None if open_raw is None else _bool(open_raw, True),
        local_accounts=_bool(_get("LOCAL_ACCOUNTS", env=env), True),
        auto_migrate=_bool(_get("AUTO_MIGRATE", env=env), True),
        max_body_mb=max_body,
        session_ttl_hours=int(_get("SESSION_TTL_HOURS", "12", env) or 12),
        cors_origins=_list(_get("CORS_ORIGINS", env=env)),
        login_rate_per_minute=int(_get("LOGIN_RATE_PER_MINUTE", "10", env) or 10),
        public_url=_get("PUBLIC_URL", env=env),
        oidc=_oidc(env),
        oauth=_oauth(env),
        ldap=_ldap(env),
        proxy=_proxy(env),
    )
