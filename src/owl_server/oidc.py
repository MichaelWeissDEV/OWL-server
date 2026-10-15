"""OpenID Connect login: discovery, authorization code flow with PKCE, ID token validation.

Uses ``PyJWT`` for signature and claim validation (never a hand-written JWT/OAuth implementation).
Algorithms are restricted to asymmetric ones (``none`` and HMAC are refused), the issuer, audience,
expiry and nonce are checked, and every login state is single use.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import delete
from sqlalchemy.orm import Session

from owl_server import models as m
from owl_server.config import OidcSettings

ALLOWED_ALGS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512")
STATE_TTL = timedelta(minutes=10)


class OidcError(Exception):
    """Login failed; ``public`` is safe to show to the user, details go to the log."""

    def __init__(self, public: str, detail: str = "") -> None:
        super().__init__(detail or public)
        self.public = public


def _pkce_challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


class OidcService:
    def __init__(self, settings: OidcSettings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=10.0, verify=settings.verify_tls)
        self._discovery: tuple[float, dict[str, Any]] | None = None
        self._jwks: tuple[float, dict[str, Any]] | None = None

    # -- provider metadata -------------------------------------------------------------

    def discovery(self) -> dict[str, Any]:
        if self._discovery and time.monotonic() - self._discovery[0] < 3600:
            return self._discovery[1]
        url = f"{self.settings.issuer}/.well-known/openid-configuration"
        try:
            response = self.client.get(url)
            response.raise_for_status()
            doc = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError(
                "The identity provider is not reachable", f"discovery failed: {exc}"
            ) from exc
        if str(doc.get("issuer", "")).rstrip("/") != self.settings.issuer:
            raise OidcError(
                "The identity provider is misconfigured", "issuer in discovery document differs"
            )
        for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if key not in doc:
                raise OidcError("The identity provider is misconfigured", f"discovery lacks {key}")
        self._discovery = (time.monotonic(), doc)
        return doc

    def _keys(self, force: bool = False) -> dict[str, Any]:
        if not force and self._jwks and time.monotonic() - self._jwks[0] < 600:
            return self._jwks[1]
        try:
            response = self.client.get(self.discovery()["jwks_uri"])
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError(
                "The identity provider is not reachable", f"jwks fetch failed: {exc}"
            ) from exc
        self._jwks = (time.monotonic(), data)
        return data

    # -- login -------------------------------------------------------------------------

    def begin(self, session: Session) -> str:
        """Create a login state and return the URL to send the browser to."""
        session.execute(delete(m.OidcState).where(m.OidcState.expires_at < m.now()))  # tidy up
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        session.add(
            m.OidcState(
                state=state,
                nonce=nonce,
                verifier=verifier,
                expires_at=(datetime.now(UTC) + STATE_TTL).isoformat(timespec="seconds"),
            )
        )
        session.flush()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "scope": self.settings.scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{self.discovery()['authorization_endpoint']}?{query}"

    def complete(self, session: Session, code: str, state: str) -> dict[str, Any]:
        """Exchange the code, validate the ID token and return its claims."""
        row = session.get(m.OidcState, state)
        if row is None:
            raise OidcError("The login attempt is unknown or was already used", "unknown state")
        session.delete(row)  # single use, even if validation fails below
        session.flush()
        if row.expires_at < m.now():
            raise OidcError("The login attempt has expired - please try again", "state expired")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
            "client_id": self.settings.client_id,
            "code_verifier": row.verifier,
        }
        auth: httpx.Auth | None = None
        if self.settings.client_secret:
            auth = httpx.BasicAuth(self.settings.client_id, self.settings.client_secret)
        try:
            response = self.client.post(
                self.discovery()["token_endpoint"],
                data=data,
                auth=auth if auth is not None else httpx.USE_CLIENT_DEFAULT,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise OidcError(
                "The identity provider is not reachable", f"token request failed: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise OidcError(
                "The identity provider rejected the login",
                f"token endpoint answered {response.status_code}",
            )
        try:
            id_token = response.json()["id_token"]
        except (ValueError, KeyError) as exc:
            raise OidcError("The identity provider returned no ID token", "no id_token") from exc
        return self.validate_id_token(id_token, row.nonce)

    def validate_id_token(self, token: str, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OidcError("The ID token is malformed", str(exc)) from exc
        alg = header.get("alg")
        if alg not in ALLOWED_ALGS:
            raise OidcError("The ID token uses a forbidden signature algorithm", f"alg={alg}")
        key = self._find_key(header.get("kid"), alg)
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[alg],
                audience=self.settings.audience or self.settings.client_id,
                issuer=self.settings.issuer,
                leeway=60,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise OidcError("The ID token is not valid", f"validation failed: {exc}") from exc
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OidcError("The ID token does not belong to this login", "nonce mismatch")
        aud = claims.get("aud")
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != self.settings.client_id:
            raise OidcError("The ID token was issued for another client", "azp mismatch")
        return claims

    def _find_key(self, kid: str | None, alg: str):  # type: ignore[no-untyped-def]
        for attempt in (False, True):  # the second pass re-fetches after a key rotation
            for jwk in self._keys(force=attempt).get("keys", []):
                if kid is None or jwk.get("kid") == kid:
                    if jwk.get("alg") not in (None, alg):
                        continue
                    try:
                        return jwt.PyJWK(jwk).key
                    except jwt.PyJWTError:
                        continue
        raise OidcError("The ID token was signed with an unknown key", f"no jwk for kid={kid}")

    # -- claims -> account -------------------------------------------------------------

    def claim_values(self, claims: dict[str, Any]) -> list[str]:
        name = self.settings.role_claim
        if not name:
            return []
        value = claims.get(name, [])
        return [str(v) for v in value] if isinstance(value, list) else [str(value)]
