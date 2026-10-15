"""Plain OAuth 2.0 sign-in (authorization code + PKCE) for providers without OpenID Connect.

The user is identified by calling the provider's user-info endpoint with the access token.
Because "anyone with an account at the provider" is rarely the intended audience, set
``OAUTH_ALLOWED_USERS`` (or leave ``AUTO_CREATE`` off and pre-create accounts).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from owl_server import models as m
from owl_server.config import OAuthSettings
from owl_server.oidc import STATE_TTL, OidcError


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


class OAuthService:
    def __init__(self, settings: OAuthSettings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=10.0, verify=settings.verify_tls)

    def begin(self, session: Session) -> str:
        session.execute(delete(m.OidcState).where(m.OidcState.expires_at < m.now()))
        state, verifier = "o" + secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        session.add(
            m.OidcState(
                state=state,
                nonce="-",
                verifier=verifier,
                expires_at=(datetime.now(UTC) + STATE_TTL).isoformat(timespec="seconds"),
            )
        )
        session.flush()
        query = {
            "response_type": "code",
            "client_id": self.settings.client_id,
            "redirect_uri": self.settings.redirect_uri,
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
        if self.settings.scopes:
            query["scope"] = self.settings.scopes
        return f"{self.settings.authorize_url}?{urlencode(query)}"

    def complete(self, session: Session, code: str, state: str) -> dict[str, Any]:
        """Exchange the code and return the user's profile (a dict)."""
        row = session.get(m.OidcState, state)
        if row is None or not state.startswith("o"):
            raise OidcError("The login attempt is unknown or was already used", "unknown state")
        session.delete(row)
        session.flush()
        if row.expires_at < m.now():
            raise OidcError("The login attempt has expired - please try again", "state expired")
        s = self.settings
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": s.redirect_uri,
            "client_id": s.client_id,
            "code_verifier": row.verifier,
        }
        if s.client_secret:
            data["client_secret"] = s.client_secret
        try:
            response = self.client.post(
                s.token_url, data=data, headers={"Accept": "application/json"}
            )
            token = response.json().get("access_token") if response.status_code < 400 else None
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError(
                "The identity provider is not reachable", f"token request failed: {exc}", status=502
            ) from exc
        if not token:
            raise OidcError("The identity provider rejected the login", "no access token")
        try:
            info = self.client.get(
                s.userinfo_url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            profile = info.json() if info.status_code < 400 else None
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError(
                "The identity provider is not reachable", f"userinfo failed: {exc}", status=502
            ) from exc
        if not isinstance(profile, dict) or s.id_field not in profile:
            raise OidcError("The identity provider returned no usable profile", "no profile")
        return profile
