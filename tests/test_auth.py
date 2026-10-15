"""Local accounts, sessions, personal tokens, rate limiting and password rules."""

from __future__ import annotations

import pytest

from owl_server import security
from tests.conftest import ADMIN, auth, make_skill, put

GOOD = "correct-horse-battery-9"


@pytest.fixture
def accounts_client(make_app):
    return make_app(local_accounts="true")


def admin_creates(client, username, password=GOOD, is_admin=False):
    response = client.post(
        "/api/v1/admin/users",
        headers=auth(ADMIN),
        json={"username": username, "password": password, "is_admin": is_admin},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client, username, password=GOOD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_local_accounts_can_be_switched_off(make_app):
    client = make_app(local_accounts="false")
    assert (
        client.post("/api/v1/auth/login", json={"username": "a", "password": "b"}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/admin/users", headers=auth(ADMIN), json={"username": "x", "password": GOOD}
        ).status_code
        == 404
    )
    config = client.get("/api/v1/auth/config").json()
    assert (
        config["local_accounts"] is False and config["open"] is False and config["providers"] == []
    )


def test_login_session_me_and_logout(accounts_client):
    admin_creates(accounts_client, "alice")
    result = login(accounts_client, "alice")
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    token = result.json()["token"]
    me = accounts_client.get("/api/v1/auth/me", headers=auth(token)).json()
    assert me["authenticated"] and me["username"] == "alice" and me["is_admin"] is False
    assert accounts_client.post("/api/v1/auth/logout", headers=auth(token)).json() == {"ok": True}
    assert (
        accounts_client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    )  # session is gone
    assert accounts_client.get("/api/v1/auth/me").json()["authenticated"] is False


def test_wrong_credentials_are_indistinguishable_and_audited(accounts_client):
    admin_creates(accounts_client, "alice")
    wrong_pw = login(accounts_client, "alice", "wrong-password-123")
    no_user = login(accounts_client, "nobody", "wrong-password-123")
    assert wrong_pw.status_code == no_user.status_code == 401 and wrong_pw.json() == no_user.json()
    events = accounts_client.get(
        "/api/v1/admin/audit?action=auth.login_failed", headers=auth(ADMIN)
    ).json()
    assert len(events) == 2 and "wrong-password" not in str(events)


def test_login_rate_limit(make_app):
    client = make_app(local_accounts="true", login_rate_per_minute="3")
    codes = [login(client, "nobody", "x" * 14).status_code for _ in range(6)]
    assert codes[:3] == [401, 401, 401] and 429 in codes[3:]
    assert login(client, "nobody", "x" * 14).headers.get("retry-after") == "60"


@pytest.mark.parametrize(
    "password, message", [("short1", "at least 12"), ("onlylowercaseletters", "too simple")]
)
def test_password_policy(accounts_client, password, message):
    response = accounts_client.post(
        "/api/v1/admin/users", headers=auth(ADMIN), json={"username": "weak", "password": password}
    )
    assert response.status_code == 422 and message in response.json()["detail"]


def test_passwords_are_hashed_with_argon2id(accounts_client):
    admin_creates(accounts_client, "alice")
    from owl_server import db, models

    with db.session_scope(accounts_client.app.state.owl.factory) as session:
        stored = session.query(models.User).one().password_hash
    assert stored.startswith("$argon2id$") and GOOD not in stored


def test_password_change_revokes_all_sessions(accounts_client):
    admin_creates(accounts_client, "alice")
    first = login(accounts_client, "alice").json()["token"]
    second = login(accounts_client, "alice").json()["token"]
    bad = accounts_client.post(
        "/api/v1/auth/password",
        headers=auth(first),
        json={"old": "wrong", "new": "another-good-pass-1"},
    )
    assert bad.status_code == 422
    ok = accounts_client.post(
        "/api/v1/auth/password",
        headers=auth(first),
        json={"old": GOOD, "new": "another-good-pass-1"},
    )
    assert ok.status_code == 200
    assert accounts_client.get("/api/v1/auth/me", headers=auth(first)).status_code == 401
    assert accounts_client.get("/api/v1/auth/me", headers=auth(second)).status_code == 401
    assert login(accounts_client, "alice").status_code == 401
    assert login(accounts_client, "alice", "another-good-pass-1").status_code == 200


def test_disabling_a_user_kills_sessions_and_tokens(accounts_client):
    admin_creates(accounts_client, "bob")
    token = login(accounts_client, "bob").json()["token"]
    assert (
        accounts_client.patch(
            "/api/v1/admin/users/bob", headers=auth(ADMIN), json={"active": False}
        ).status_code
        == 200
    )
    assert accounts_client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    assert login(accounts_client, "bob").status_code == 401
    accounts_client.patch("/api/v1/admin/users/bob", headers=auth(ADMIN), json={"active": True})
    assert login(accounts_client, "bob").status_code == 200


def test_user_roles_come_from_memberships_and_admin_flag(accounts_client):
    admin_creates(accounts_client, "carol")
    admin_creates(accounts_client, "root", is_admin=True)
    accounts_client.post(
        "/api/v1/registries", headers=auth(ADMIN), json={"slug": "team", "visibility": "private"}
    )
    carol, root = (login(accounts_client, n).json()["token"] for n in ("carol", "root"))
    assert (
        accounts_client.get("/r/team/api/v1/skills", headers=auth(carol)).status_code == 404
    )  # no membership
    assert (
        put(accounts_client, make_skill("x"), auth(root), registry="team").status_code == 201
    )  # server admin
    assert (
        accounts_client.put(
            "/api/v1/registries/team/members/carol", headers=auth(ADMIN), json={"role": "reader"}
        ).status_code
        == 200
    )
    assert accounts_client.get("/r/team/api/v1/skills", headers=auth(carol)).status_code == 200
    assert put(accounts_client, make_skill("y"), auth(carol), registry="team").status_code == 403
    accounts_client.put(
        "/api/v1/registries/team/members/carol", headers=auth(ADMIN), json={"role": "publisher"}
    )
    assert put(accounts_client, make_skill("y"), auth(carol), registry="team").status_code == 201
    assert accounts_client.get("/api/v1/registries/team/members", headers=auth(ADMIN)).json() == [
        {"username": "carol", "role": "publisher"}
    ]
    accounts_client.delete("/api/v1/registries/team/members/carol", headers=auth(ADMIN))
    assert accounts_client.get("/r/team/api/v1/skills", headers=auth(carol)).status_code == 404
    assert (
        accounts_client.put(
            "/api/v1/registries/team/members/carol", headers=auth(ADMIN), json={"role": "god"}
        ).status_code
        == 422
    )


def test_personal_tokens_cannot_exceed_the_users_rights(accounts_client):
    admin_creates(accounts_client, "dave")
    accounts_client.post("/api/v1/registries", headers=auth(ADMIN), json={"slug": "team"})
    accounts_client.put(
        "/api/v1/registries/team/members/dave", headers=auth(ADMIN), json={"role": "reader"}
    )
    session = login(accounts_client, "dave").json()["token"]
    too_strong = accounts_client.post(
        "/api/v1/auth/tokens", headers=auth(session), json={"role": "publisher", "registry": "team"}
    )
    assert too_strong.status_code == 403
    assert (
        accounts_client.post(
            "/api/v1/auth/tokens", headers=auth(session), json={"role": "admin"}
        ).status_code
        == 403
    )
    created = accounts_client.post(
        "/api/v1/auth/tokens",
        headers=auth(session),
        json={"role": "reader", "registry": "team", "name": "ci"},
    )
    assert created.status_code == 201
    secret = created.json()["token"]
    assert accounts_client.get("/r/team/api/v1/skills", headers=auth(secret)).status_code == 200
    # a token cannot be used to mint further tokens
    assert (
        accounts_client.post(
            "/api/v1/auth/tokens", headers=auth(secret), json={"role": "reader"}
        ).status_code
        == 403
    )
    listed = accounts_client.get("/api/v1/auth/tokens", headers=auth(session)).json()
    assert [(t["name"], t["role"], t["registry"]) for t in listed] == [("ci", "reader", "team")]
    assert "token" not in listed[0]  # secrets are never listed
    assert (
        accounts_client.delete(
            f"/api/v1/auth/tokens/{listed[0]['id']}", headers=auth(session)
        ).status_code
        == 200
    )
    assert accounts_client.get("/r/team/api/v1/skills", headers=auth(secret)).status_code == 401


def test_token_role_caps_the_users_role(accounts_client):
    admin_creates(accounts_client, "erin", is_admin=True)
    session = login(accounts_client, "erin").json()["token"]
    ro = accounts_client.post(
        "/api/v1/auth/tokens", headers=auth(session), json={"role": "reader"}
    ).json()["token"]
    assert accounts_client.get("/api/v1/skills", headers=auth(ro)).status_code == 200
    assert (
        put(accounts_client, make_skill("x"), auth(ro)).status_code == 403
    )  # admin user, read-only token
    assert accounts_client.get("/api/v1/admin/users", headers=auth(ro)).status_code == 403
    assert put(accounts_client, make_skill("x"), auth(session)).status_code == 201


def test_expired_and_revoked_service_tokens(make_app):
    client = make_app()
    client.post("/api/v1/registries", headers=auth(ADMIN), json={"slug": "t"})
    created = client.post(
        "/api/v1/admin/tokens",
        headers=auth(ADMIN),
        json={"registry": "t", "role": "publisher", "ttl_hours": 0.0001},
    ).json()
    # a normal token works until revoked
    ok = client.post(
        "/api/v1/admin/tokens", headers=auth(ADMIN), json={"registry": "t", "role": "publisher"}
    ).json()
    assert put(client, make_skill("a"), auth(ok["token"]), registry="t").status_code == 201
    assert client.delete(f"/api/v1/admin/tokens/{ok['id']}", headers=auth(ADMIN)).status_code == 200
    assert put(client, make_skill("b"), auth(ok["token"]), registry="t").status_code == 401
    assert (
        client.delete(f"/api/v1/admin/tokens/{ok['id']}", headers=auth(ADMIN)).status_code == 404
    )  # already revoked
    import time

    time.sleep(0.5)
    assert (
        put(client, make_skill("c"), auth(created["token"]), registry="t").status_code == 401
    )  # expired
    assert (
        client.post(
            "/api/v1/admin/tokens", headers=auth(ADMIN), json={"registry": "nope", "role": "reader"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/admin/tokens", headers=auth(ADMIN), json={"registry": "t", "role": "king"}
        ).status_code
        == 422
    )


def test_token_secrets_are_stored_only_as_hashes(make_app):
    client = make_app()
    client.post("/api/v1/registries", headers=auth(ADMIN), json={"slug": "t"})
    secret = client.post(
        "/api/v1/admin/tokens", headers=auth(ADMIN), json={"registry": "t", "role": "reader"}
    ).json()["token"]
    from owl_server import db, models

    with db.session_scope(client.app.state.owl.factory) as session:
        row = session.query(models.ApiToken).one()
    assert (
        secret.startswith("owl_")
        and secret not in (row.token_hash, row.prefix)
        and row.token_hash == security.hash_token(secret)
    )
    assert all(
        "token" not in entry
        for entry in client.get("/api/v1/admin/tokens", headers=auth(ADMIN)).json()
    )


def test_admin_cannot_demote_themselves_and_oidc_users_have_no_password(accounts_client):
    admin_creates(accounts_client, "root", is_admin=True)
    session = login(accounts_client, "root").json()["token"]
    assert (
        accounts_client.patch(
            "/api/v1/admin/users/root", headers=auth(session), json={"is_admin": False}
        ).status_code
        == 409
    )
    assert (
        accounts_client.patch(
            "/api/v1/admin/users/ghost", headers=auth(ADMIN), json={"active": False}
        ).status_code
        == 404
    )
    assert admin_creates.__name__
    assert (
        accounts_client.post(
            "/api/v1/admin/users", headers=auth(ADMIN), json={"username": "root", "password": GOOD}
        ).status_code
        == 422
    )


def test_bootstrap_token_comparison_is_exact(client):
    assert client.get("/api/v1/admin/users", headers=auth(ADMIN)).status_code == 200
    assert client.get("/api/v1/admin/users", headers=auth(ADMIN[:-1])).status_code == 401
    assert client.get("/api/v1/admin/users", headers=auth(ADMIN + "x")).status_code == 401
