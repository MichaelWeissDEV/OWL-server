"""Configuration from environment variables (``OWL_SERVER_*``), with Docker-secret support.

Every variable ``X`` can also be given as ``X_FILE`` pointing at a file whose content is the value,
which keeps secrets out of the process environment and of ``docker inspect``.
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
    #: IdP group/role value -> "admin"; anyone else becomes an ordinary user
    admin_values: list[str] = field(default_factory=list)
    #: IdP group/role value -> {registry slug: role}
    registry_roles: dict[str, dict[str, str]] = field(default_factory=dict)
    verify_tls: bool = True


@dataclass
class Settings:
    database_url: str
    mode: str = "mixed"
    default_registry: str = "default"
    admin_token: str | None = None
    local_accounts: bool = False
    auto_migrate: bool = True
    max_body_mb: int = 40
    session_ttl_hours: int = 12
    cors_origins: list[str] = field(default_factory=list)
    login_rate_per_minute: int = 10
    public_url: str | None = None
    oidc: OidcSettings | None = None

    @property
    def max_body_bytes(self) -> int:
        return self.max_body_mb * 1024 * 1024


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
    oidc = None
    issuer = _get("OIDC_ISSUER", env=env)
    if issuer:
        client_id = _get("OIDC_CLIENT_ID", env=env)
        redirect = _get("OIDC_REDIRECT_URI", env=env)
        if not client_id or not redirect:
            raise ConfigError(
                "OIDC needs OWL_SERVER_OIDC_CLIENT_ID and OWL_SERVER_OIDC_REDIRECT_URI"
            )
        if not issuer.startswith("https://") and not _bool(
            _get("OIDC_ALLOW_INSECURE", env=env), False
        ):
            raise ConfigError("OWL_SERVER_OIDC_ISSUER must be an https:// URL")
        try:
            registry_roles = json.loads(_get("OIDC_REGISTRY_ROLES", "{}", env) or "{}")
        except ValueError as exc:
            raise ConfigError(f"OWL_SERVER_OIDC_REGISTRY_ROLES is not valid JSON: {exc}") from exc
        oidc = OidcSettings(
            issuer=issuer.rstrip("/"),
            client_id=client_id,
            client_secret=_get("OIDC_CLIENT_SECRET", env=env),
            redirect_uri=redirect,
            scopes=_get("OIDC_SCOPES", "openid profile email", env) or "openid",
            audience=_get("OIDC_AUDIENCE", env=env),
            username_claim=_get("OIDC_USERNAME_CLAIM", "preferred_username", env)
            or "preferred_username",
            role_claim=_get("OIDC_ROLE_CLAIM", env=env),
            admin_values=[
                v for v in (_get("OIDC_ADMIN_VALUES", "", env) or "").split(",") if v.strip()
            ],
            registry_roles=registry_roles,
            verify_tls=_bool(_get("OIDC_VERIFY_TLS", env=env), True),
        )
    return Settings(
        database_url=database_url,
        mode=mode,
        default_registry=_get("DEFAULT_REGISTRY", "default", env) or "default",
        admin_token=admin_token,
        local_accounts=_bool(_get("LOCAL_ACCOUNTS", env=env), False),
        auto_migrate=_bool(_get("AUTO_MIGRATE", env=env), True),
        max_body_mb=max_body,
        session_ttl_hours=int(_get("SESSION_TTL_HOURS", "12", env) or 12),
        cors_origins=[o for o in (_get("CORS_ORIGINS", "", env) or "").split(",") if o.strip()],
        login_rate_per_minute=int(_get("LOGIN_RATE_PER_MINUTE", "10", env) or 10),
        public_url=_get("PUBLIC_URL", env=env),
        oidc=oidc,
    )
