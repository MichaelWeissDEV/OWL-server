"""OpenID Connect against a mocked identity provider (real RSA signatures, PKCE, nonce, JWKS)."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from owl_server.app import create_app
from owl_server.config import load_settings
from tests.conftest import ADMIN, auth, make_skill, put

ISSUER = "https://idp.example.com/realms/owl"
CLIENT_ID = "owl-server"
REDIRECT = "https://dashboard.example.com/callback"


def jwk_for(key, kid):
    public = key.public_key().public_numbers()

    def b64(n: int) -> str:
        return (
            base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big"))
            .rstrip(b"=")
            .decode()
        )

    return {
        "kty": "RSA",
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
        "n": b64(public.n),
        "e": b64(public.e),
    }


class FakeIdP:
    """Discovery, JWKS and token endpoint in one mock transport."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "key-1"
        self.up = True
        self.claims = {
            "sub": "user-123",
            "preferred_username": "olivia",
            "email": "olivia@example.com",
            "groups": ["owl-publishers"],
        }
        self.override: dict = {}
        self.sign_key = self.key
        self.alg = "RS256"
        self.jwks_calls = 0
        self.last_auth_request: dict | None = None
        self.token_requests: list[dict] = []
        self.nonce = ""
        self.discovery_issuer = ISSUER

    def id_token(self, nonce: str) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            **self.claims,
        }
        claims.update(self.override)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.sign_key, algorithm=self.alg, headers={"kid": self.kid})

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("idp down")
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": self.discovery_issuer,
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/certs",
                },
            )
        if path.endswith("/certs"):
            self.jwks_calls += 1
            return httpx.Response(200, json={"keys": [jwk_for(self.key, self.kid)]})
        if path.endswith("/token"):
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(
                {**form, "authorization": request.headers.get("authorization")}
            )
            return httpx.Response(
                200, json={"id_token": self.id_token(self.nonce), "access_token": "ignored"}
            )
        return httpx.Response(404)


@pytest.fixture
def idp():
    return FakeIdP()


@pytest.fixture
def oidc_client(make_app, database_url, idp):
    from fastapi.testclient import TestClient

    env = {
        "OWL_SERVER_DATABASE_URL": database_url,
        "OWL_SERVER_ADMIN_TOKEN": ADMIN,
        "OWL_SERVER_OIDC_ISSUER": ISSUER,
        "OWL_SERVER_OIDC_CLIENT_ID": CLIENT_ID,
        "OWL_SERVER_OIDC_CLIENT_SECRET": "s3cret",
        "OWL_SERVER_OIDC_REDIRECT_URI": REDIRECT,
        "OWL_SERVER_OIDC_ROLE_CLAIM": "groups",
        "OWL_SERVER_OIDC_ADMIN_VALUES": "owl-admins",
        "OWL_SERVER_OIDC_REGISTRY_ROLES": json.dumps(
            {"owl-publishers": {"team": "publisher"}, "owl-readers": {"team": "reader"}}
        ),
    }
    http = httpx.Client(transport=httpx.MockTransport(idp.handler))
    client = TestClient(create_app(load_settings(env), oidc_client=http))
    client.post(
        "/api/v1/registries", headers=auth(ADMIN), json={"slug": "team", "visibility": "private"}
    )
    return client


def start(client, idp):
    """Begin a login; returns the authorization request parameters and remembers the nonce."""
    url = client.get("/api/v1/auth/oidc/login?json=1").json()["authorization_url"]
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    idp.nonce = params["nonce"]
    idp.last_auth_request = params
    return params


def finish(client, params, code="authcode"):
    return client.post("/api/v1/auth/oidc/exchange", json={"code": code, "state": params["state"]})


def test_auth_config_advertises_oidc(oidc_client):
    assert oidc_client.get("/api/v1/auth/config").json()["oidc"] is True


def test_authorization_request_uses_pkce_state_and_nonce(oidc_client, idp):
    params = start(oidc_client, idp)
    assert (
        params["response_type"] == "code"
        and params["client_id"] == CLIENT_ID
        and params["redirect_uri"] == REDIRECT
    )
    assert (
        params["code_challenge_method"] == "S256"
        and len(params["state"]) > 20
        and len(params["nonce"]) > 20
    )
    redirect = oidc_client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert redirect.status_code == 302 and redirect.headers["location"].startswith(
        f"{ISSUER}/auth?"
    )


def test_successful_login_creates_user_session_and_maps_roles(oidc_client, idp):
    params = start(oidc_client, idp)
    result = finish(oidc_client, params)
    assert result.status_code == 200, result.text
    token = result.json()["token"]
    # the token exchange carried the PKCE verifier matching the challenge, and the client secret
    sent = idp.token_requests[0]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(sent["code_verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == params["code_challenge"] and sent["grant_type"] == "authorization_code"
    assert sent["redirect_uri"] == REDIRECT and sent["authorization"].startswith("Basic ")
    me = oidc_client.get("/api/v1/auth/me", headers=auth(token)).json()
    assert me["username"] == "olivia" and me["is_admin"] is False
    assert me["memberships"] == [{"registry": "team", "role": "publisher"}]
    assert put(oidc_client, make_skill("by-oidc"), auth(token), registry="team").status_code == 201
    assert oidc_client.get("/api/v1/admin/users", headers=auth(token)).status_code == 403
    admin_view = oidc_client.get("/api/v1/admin/users", headers=auth(ADMIN)).json()
    assert admin_view[0]["provider"] == "oidc" and "password" not in str(admin_view)


def test_group_mapping_is_refreshed_on_every_login(oidc_client, idp):
    finish(oidc_client, start(oidc_client, idp))
    idp.claims["groups"] = ["owl-admins", "owl-readers"]
    token = finish(oidc_client, start(oidc_client, idp)).json()["token"]
    me = oidc_client.get("/api/v1/auth/me", headers=auth(token)).json()
    assert me["is_admin"] is True and me["memberships"] == [{"registry": "team", "role": "reader"}]
    idp.claims["groups"] = []
    me = oidc_client.get(
        "/api/v1/auth/me",
        headers=auth(finish(oidc_client, start(oidc_client, idp)).json()["token"]),
    ).json()
    assert me["is_admin"] is False


def test_state_is_single_use_and_unknown_states_are_refused(oidc_client, idp):
    params = start(oidc_client, idp)
    assert finish(oidc_client, params).status_code == 200
    replay = finish(oidc_client, params)
    assert replay.status_code == 401 and "already used" in replay.json()["detail"]
    assert (
        oidc_client.post(
            "/api/v1/auth/oidc/exchange", json={"code": "x", "state": "forged"}
        ).status_code
        == 401
    )
    assert oidc_client.post("/api/v1/auth/oidc/exchange", json={}).status_code == 401


def test_expired_state(oidc_client, idp):
    params = start(oidc_client, idp)
    from owl_server import db, models

    with db.session_scope(oidc_client.app.state.owl.factory) as session:
        session.get(models.OidcState, params["state"]).expires_at = "2000-01-01T00:00:00+00:00"
    assert "expired" in finish(oidc_client, params).json()["detail"]


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda i: i.override.update(iss="https://evil.example.com"), "not valid"),
        (lambda i: i.override.update(aud="someone-else"), "not valid"),
        (lambda i: i.override.update(exp=int(time.time()) - 3600), "not valid"),
        (lambda i: i.override.update(nonce="wrong-nonce"), "does not belong"),
        (lambda i: i.override.update(sub=None), "not valid"),
    ],
)
def test_invalid_id_tokens_are_rejected(oidc_client, idp, mutate, expected):
    mutate(idp)
    result = finish(oidc_client, start(oidc_client, idp))
    assert result.status_code == 401 and expected in result.json()["detail"]
    assert (
        oidc_client.get("/api/v1/admin/users", headers=auth(ADMIN)).json() == []
    )  # no account was created


def test_token_signed_with_another_key_is_rejected(oidc_client, idp):
    idp.sign_key = idp.other_key
    result = finish(oidc_client, start(oidc_client, idp))
    assert result.status_code == 401 and "not valid" in result.json()["detail"]


def test_none_and_hmac_algorithms_are_refused(oidc_client, idp):
    idp.alg = "HS256"
    idp.sign_key = "shared-secret-shared-secret-shared-secret"
    assert (
        "forbidden signature algorithm"
        in finish(oidc_client, start(oidc_client, idp)).json()["detail"]
    )
    idp.alg = "none"
    idp.sign_key = None
    # PyJWT cannot even produce "none" with a key; craft it by hand
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "kid": "key-1"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"iss": ISSUER, "aud": CLIENT_ID, "sub": "x", "exp": 9999999999, "iat": 1}
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    from owl_server.oidc import OidcError

    with pytest.raises(OidcError) as excinfo:
        oidc_client.app.state.owl.oidc.validate_id_token(f"{header}.{payload}.", "n")
    assert "forbidden" in excinfo.value.public


def test_key_rotation_triggers_a_jwks_refresh(oidc_client, idp):
    finish(oidc_client, start(oidc_client, idp))
    before = idp.jwks_calls
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.key, idp.sign_key, idp.kid = new_key, new_key, "key-2"
    result = finish(oidc_client, start(oidc_client, idp))
    assert result.status_code == 200 and idp.jwks_calls > before


def test_unreachable_idp_is_reported_without_internals(oidc_client, idp):
    idp.up = False
    response = oidc_client.get("/api/v1/auth/oidc/login?json=1")
    assert (
        response.status_code == 502
        and "not reachable" in response.json()["detail"]
        and "idp down" not in response.text
    )
    idp.up = True
    params = start(oidc_client, idp)
    idp.up = False
    assert finish(oidc_client, params).status_code == 502


def test_discovery_issuer_mismatch_is_refused(oidc_client, idp):
    idp.discovery_issuer = "https://attacker.example.com"
    assert oidc_client.get("/api/v1/auth/oidc/login?json=1").status_code == 502


def test_oidc_user_cannot_log_in_with_a_password_and_disabled_users_are_blocked(oidc_client, idp):
    finish(oidc_client, start(oidc_client, idp))
    assert (
        oidc_client.post(
            "/api/v1/auth/login", json={"username": "olivia", "password": "x" * 14}
        ).status_code
        == 401
    )
    oidc_client.patch("/api/v1/admin/users/olivia", headers=auth(ADMIN), json={"active": False})
    assert finish(oidc_client, start(oidc_client, idp)).status_code == 403
    assert (
        oidc_client.patch(
            "/api/v1/admin/users/olivia", headers=auth(ADMIN), json={"password": "new-pass-123456"}
        ).status_code
        == 422
    )


def test_username_clash_with_a_local_account_gets_a_suffix(make_app, database_url, idp):
    from fastapi.testclient import TestClient

    env = {
        "OWL_SERVER_DATABASE_URL": database_url,
        "OWL_SERVER_ADMIN_TOKEN": ADMIN,
        "OWL_SERVER_LOCAL_ACCOUNTS": "true",
        "OWL_SERVER_OIDC_ISSUER": ISSUER,
        "OWL_SERVER_OIDC_CLIENT_ID": CLIENT_ID,
        "OWL_SERVER_OIDC_REDIRECT_URI": REDIRECT,
    }
    client = TestClient(
        create_app(
            load_settings(env), oidc_client=httpx.Client(transport=httpx.MockTransport(idp.handler))
        )
    )
    client.post(
        "/api/v1/admin/users",
        headers=auth(ADMIN),
        json={"username": "olivia", "password": "correct-horse-battery-9"},
    )
    token = finish(client, start(client, idp)).json()["token"]
    assert client.get("/api/v1/auth/me", headers=auth(token)).json()["username"] == "olivia@oidc"


def test_oidc_disabled_returns_404(client):
    assert client.get("/api/v1/auth/oidc/login").status_code == 404
    assert (
        client.post("/api/v1/auth/oidc/exchange", json={"code": "x", "state": "y"}).status_code
        == 404
    )
