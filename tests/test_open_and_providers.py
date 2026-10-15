"""Open-by-default operation, the secure-this-server step, and external identity providers."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from ldap3 import MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server

from owl_server.app import create_app
from owl_server.config import ConfigError, load_settings
from tests.conftest import ADMIN, auth, make_skill, put

GOOD = "correct-horse-battery-9"


def bare(make_app, **overrides):
    """An app without an admin token and with nothing configured - the out-of-the-box state."""
    env = {"OWL_SERVER_ADMIN_TOKEN": "", **{k: v for k, v in overrides.items()}}
    return make_app(**{k.removeprefix("OWL_SERVER_").lower(): v for k, v in env.items()})


@pytest.fixture
def open_client(make_app, database_url):
    settings = load_settings({"OWL_SERVER_DATABASE_URL": database_url})
    client = TestClient(create_app(settings))
    yield client
    client.close()


# -- open mode ----------------------------------------------------------------------------------
def test_default_server_is_open_and_says_so(open_client):
    status = open_client.get("/api/v1/setup/status").json()
    assert (
        status["open"] is True
        and "nothing to authenticate" in status["reason"]
        and status["users"] == 0
    )
    me = open_client.get("/api/v1/auth/me").json()
    assert me["kind"] == "open" and me["is_admin"] is True
    config = open_client.get("/api/v1/auth/config").json()
    assert config["open"] is True and config["providers"] == []


def test_open_mode_needs_no_credentials_for_anything(open_client):
    assert (
        open_client.post(
            "/api/v1/registries", json={"slug": "team", "visibility": "private"}
        ).status_code
        == 201
    )
    assert put(open_client, make_skill("s"), {}, registry="team").status_code == 201
    assert open_client.get("/r/team/api/v1/skills").json()[0]["name"] == "s"
    assert (
        open_client.post(
            "/api/v1/admin/users", json={"username": "u1", "password": GOOD}
        ).status_code
        == 201
    )
    assert open_client.get("/api/v1/admin/audit").status_code == 200
    audit = open_client.get("/api/v1/admin/audit").json()
    assert any(e["actor"] == "open:open-mode" for e in audit)  # actions are still attributed
    # a stale or invalid token must not lock anybody out of an open server
    assert open_client.get("/api/v1/skills", headers=auth("owl_stale")).status_code == 200


def test_configuring_a_way_to_log_in_secures_the_server(make_app):
    assert (
        make_app().get("/api/v1/setup/status").json()["open"] is False
    )  # admin token present (fixture default)


def test_environment_can_force_either_state(make_app, database_url):
    forced_open = TestClient(
        create_app(
            load_settings(
                {
                    "OWL_SERVER_DATABASE_URL": database_url,
                    "OWL_SERVER_ADMIN_TOKEN": ADMIN,
                    "OWL_SERVER_OPEN": "true",
                }
            )
        )
    )
    assert forced_open.get("/api/v1/skills").status_code == 200
    assert "forced" in forced_open.get("/api/v1/setup/status").json()["reason"]
    forced_closed = TestClient(
        create_app(
            load_settings({"OWL_SERVER_DATABASE_URL": database_url, "OWL_SERVER_OPEN": "false"})
        )
    )
    assert forced_closed.get("/api/v1/skills").status_code == 401


def test_secure_step_creates_the_first_admin_and_closes_the_server(open_client):
    put(open_client, make_skill("kept"), {})
    weak = open_client.post("/api/v1/setup/secure", json={"username": "root", "password": "short"})
    assert weak.status_code == 422
    assert open_client.get("/api/v1/setup/status").json()["open"] is True  # nothing changed
    done = open_client.post("/api/v1/setup/secure", json={"username": "root", "password": GOOD})
    assert done.status_code == 201
    token = done.json()["token"]
    # from now on: authentication required, content is kept
    assert open_client.get("/api/v1/skills").status_code == 401
    assert open_client.get("/api/v1/admin/users").status_code == 401
    assert open_client.get("/api/v1/skills", headers=auth(token)).json()[0]["name"] == "kept"
    assert open_client.get("/api/v1/setup/status").json()["open"] is False
    assert (
        open_client.post(
            "/api/v1/setup/secure", json={"username": "x", "password": GOOD}
        ).status_code
        == 409
    )
    assert (
        open_client.post(
            "/api/v1/auth/login", json={"username": "root", "password": GOOD}
        ).status_code
        == 200
    )
    events = open_client.get(
        "/api/v1/admin/audit?action=server.secured", headers=auth(token)
    ).json()
    assert events and GOOD not in str(events)


def test_secure_step_refused_when_forced_open_or_without_local_accounts(make_app, database_url):
    forced = TestClient(
        create_app(
            load_settings({"OWL_SERVER_DATABASE_URL": database_url, "OWL_SERVER_OPEN": "true"})
        )
    )
    assert (
        forced.post("/api/v1/setup/secure", json={"username": "r", "password": GOOD}).status_code
        == 409
    )
    nolocal = TestClient(
        create_app(
            load_settings(
                {
                    "OWL_SERVER_DATABASE_URL": database_url,
                    "OWL_SERVER_LOCAL_ACCOUNTS": "false",
                    "OWL_SERVER_OPEN": "",
                }
            )
        )
    )
    assert (
        nolocal.post("/api/v1/setup/secure", json={"username": "r", "password": GOOD}).status_code
        == 409
    )


def test_security_switch_from_the_dashboard(open_client):
    assert (
        open_client.put("/api/v1/admin/security", json={"open": False}).status_code == 422
    )  # nobody could log in
    open_client.post(
        "/api/v1/admin/users", json={"username": "boss", "password": GOOD, "is_admin": True}
    )
    assert open_client.put("/api/v1/admin/security", json={"open": False}).json()["open"] is False
    assert open_client.get("/api/v1/skills").status_code == 401
    token = open_client.post(
        "/api/v1/auth/login", json={"username": "boss", "password": GOOD}
    ).json()["token"]
    refused = open_client.put("/api/v1/admin/security", headers=auth(token), json={"open": True})
    assert refused.status_code == 422 and "confirm" in refused.json()["detail"]
    assert (
        open_client.put(
            "/api/v1/admin/security", headers=auth(token), json={"open": True, "confirm": True}
        ).json()["open"]
        is True
    )
    assert open_client.get("/api/v1/skills").status_code == 200


def test_security_switch_is_blocked_by_environment_override(make_app):
    client = make_app(open="false")
    assert (
        client.put(
            "/api/v1/admin/security", headers=auth(ADMIN), json={"open": True, "confirm": True}
        ).status_code
        == 409
    )


def test_user_management_for_the_dashboard(make_app):
    client = make_app()
    h = auth(ADMIN)
    client.post("/api/v1/registries", headers=h, json={"slug": "team"})
    client.post("/api/v1/admin/users", headers=h, json={"username": "carol", "password": GOOD})
    client.put("/api/v1/registries/team/members/carol", headers=h, json={"role": "publisher"})
    listed = client.get("/api/v1/admin/users", headers=h).json()
    assert listed[0]["username"] == "carol" and listed[0]["memberships"] == [
        {"registry": "team", "role": "publisher"}
    ]
    assert client.get("/api/v1/admin/users/carol", headers=h).json()["provider"] == "local"
    assert client.get("/api/v1/admin/users/ghost", headers=h).status_code == 404
    login = client.post("/api/v1/auth/login", json={"username": "carol", "password": GOOD}).json()[
        "token"
    ]
    assert (
        client.delete("/api/v1/admin/users/carol", headers=auth(login)).status_code == 403
    )  # not an admin
    assert client.delete("/api/v1/admin/users/carol", headers=h).status_code == 200
    assert (
        client.get("/api/v1/auth/me", headers=auth(login)).status_code == 401
    )  # tokens went with the account
    assert client.get("/api/v1/registries/team/members", headers=h).json() == []
    client.post(
        "/api/v1/admin/users",
        headers=h,
        json={"username": "root", "password": GOOD, "is_admin": True},
    )
    root = client.post("/api/v1/auth/login", json={"username": "root", "password": GOOD}).json()[
        "token"
    ]
    assert (
        client.delete("/api/v1/admin/users/root", headers=auth(root)).status_code == 409
    )  # not yourself
    assert client.delete("/api/v1/admin/users/ghost", headers=h).status_code == 404


def test_server_info_has_no_secrets(make_app):
    info = make_app(local_accounts="true").get("/api/v1/admin/server", headers=auth(ADMIN)).json()
    assert info["counts"]["registries"] == 1 and info["providers"]["admin_token"] is True
    assert info["schema_revision"]
    assert not any(k in json.dumps(info).lower() for k in ("password", "secret", "client_secret"))
    assert ADMIN not in json.dumps(info)


# -- OAuth 2.0 (GitHub preset) --------------------------------------------------------------------
class FakeOAuth:
    def __init__(self):
        self.profile = {"id": 4711, "login": "octo", "email": "octo@example.com"}
        self.token_status = 200
        self.userinfo_status = 200
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "github.com":
            return httpx.Response(
                self.token_status, json={"access_token": "gho_x"} if self.token_status < 400 else {}
            )
        if request.url.host == "api.github.com":
            assert request.headers["authorization"] == "Bearer gho_x"
            return httpx.Response(self.userinfo_status, json=self.profile)
        return httpx.Response(404)


@pytest.fixture
def oauth(database_url):
    fake = FakeOAuth()
    env = {
        "OWL_SERVER_DATABASE_URL": database_url,
        "OWL_SERVER_ADMIN_TOKEN": ADMIN,
        "OWL_SERVER_OAUTH_PRESET": "github",
        "OWL_SERVER_OAUTH_CLIENT_ID": "cid",
        "OWL_SERVER_OAUTH_CLIENT_SECRET": "sec",
        "OWL_SERVER_OAUTH_REDIRECT_URI": "https://dash.example.com/cb",
        "OWL_SERVER_OAUTH_ALLOWED_USERS": "octo,monalisa",
    }
    app = create_app(
        load_settings(env), oauth_client=httpx.Client(transport=httpx.MockTransport(fake.handler))
    )
    return TestClient(app), fake


def sso_start(client):
    url = client.get("/api/v1/auth/sso/oauth/login?json=1").json()["authorization_url"]
    from urllib.parse import parse_qs, urlparse

    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}, url


def test_oauth_github_flow(oauth):
    client, fake = oauth
    config = client.get("/api/v1/auth/config").json()
    assert config["providers"] == [
        {"id": "oauth", "type": "oauth2", "label": "Sign in with GitHub"}
    ]
    params, url = sso_start(client)
    assert (
        url.startswith("https://github.com/login/oauth/authorize?")
        and params["code_challenge_method"] == "S256"
    )
    assert params["scope"] == "read:user user:email" and params["client_id"] == "cid"
    result = client.post(
        "/api/v1/auth/sso/oauth/exchange", json={"code": "abc", "state": params["state"]}
    )
    assert result.status_code == 200, result.text
    token_request = next(r for r in fake.requests if r.url.path.endswith("access_token"))
    form = dict(x.split("=") for x in token_request.content.decode().split("&"))
    assert (
        form["code_verifier"]
        and form["client_secret"] == "sec"
        and form["grant_type"] == "authorization_code"
    )
    me = client.get("/api/v1/auth/me", headers=auth(result.json()["token"])).json()
    assert (
        me["username"] == "octo" and me["memberships"] == [] and me["is_admin"] is False
    )  # no rights by default
    replay = client.post(
        "/api/v1/auth/sso/oauth/exchange", json={"code": "abc", "state": params["state"]}
    )
    assert replay.status_code == 401  # state is single use


def test_oauth_allowed_users_and_failures(oauth):
    client, fake = oauth
    fake.profile = {"id": 666, "login": "stranger"}
    params, _ = sso_start(client)
    denied = client.post(
        "/api/v1/auth/sso/oauth/exchange", json={"code": "c", "state": params["state"]}
    )
    assert denied.status_code == 403
    assert (
        client.get("/api/v1/admin/users", headers=auth(ADMIN)).json() == []
    )  # no account was created
    fake.token_status = 400
    params, _ = sso_start(client)
    assert (
        client.post(
            "/api/v1/auth/sso/oauth/exchange", json={"code": "c", "state": params["state"]}
        ).status_code
        == 401
    )
    fake.token_status = 200
    fake.userinfo_status = 500
    params, _ = sso_start(client)
    assert (
        client.post(
            "/api/v1/auth/sso/oauth/exchange", json={"code": "c", "state": params["state"]}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/auth/sso/oidc/login").status_code == 404  # not configured
    assert (
        client.post(
            "/api/v1/auth/sso/oauth/exchange", json={"code": "c", "state": "oforged"}
        ).status_code
        == 401
    )


def test_oauth_oidc_states_cannot_be_mixed_up(oauth):
    client, _fake = oauth
    assert (
        client.post(
            "/api/v1/auth/sso/oauth/exchange", json={"code": "c", "state": "not-an-oauth-state"}
        ).status_code
        == 401
    )


# -- LDAP / Active Directory (offline mock directory) ---------------------------------------------
BASE = "dc=corp,dc=example"


@pytest.fixture
def directory():
    server = Server("mock-ad", get_info=OFFLINE_AD_2012_R2)
    boot = Connection(
        server, user="cn=admin,dc=corp,dc=example", password="admin-pw", client_strategy=MOCK_SYNC
    )
    add = boot.strategy.add_entry
    add(
        "cn=admin,dc=corp,dc=example",
        {"userPassword": "admin-pw", "objectClass": "person", "sAMAccountName": "svc"},
    )
    add(
        f"cn=Alice A,ou=people,{BASE}",
        {
            "userPassword": "alice-secret-1",
            "objectClass": "person",
            "sAMAccountName": "alice",
            "mail": "alice@corp.example",
            "memberOf": [f"cn=owl-admins,ou=groups,{BASE}", f"cn=owl-publishers,ou=groups,{BASE}"],
        },
    )
    add(
        f"cn=Bob B,ou=people,{BASE}",
        {
            "userPassword": "bob-secret-12",
            "objectClass": "person",
            "sAMAccountName": "bob",
            "mail": "bob@corp.example",
            "memberOf": [f"cn=owl-readers,ou=groups,{BASE}"],
        },
    )
    add(
        f"cn=Bob Twin,ou=people,{BASE}",
        {"userPassword": "twin-secret-1", "objectClass": "person", "sAMAccountName": "twin"},
    )
    add(
        f"cn=Bob Twin2,ou=people,{BASE}",
        {"userPassword": "twin-secret-2", "objectClass": "person", "sAMAccountName": "twin"},
    )
    calls: list[str] = []

    def factory(user, password):
        calls.append(user)
        return Connection(server, user=user, password=password, client_strategy=MOCK_SYNC)

    return factory, calls


@pytest.fixture
def ldap_client(database_url, directory):
    factory, _calls = directory
    env = {
        "OWL_SERVER_DATABASE_URL": database_url,
        "OWL_SERVER_ADMIN_TOKEN": ADMIN,
        "OWL_SERVER_LDAP_URL": "ldaps://dc.corp.example",
        "OWL_SERVER_LDAP_BIND_DN": "cn=admin,dc=corp,dc=example",
        "OWL_SERVER_LDAP_BIND_PASSWORD": "admin-pw",
        "OWL_SERVER_LDAP_USER_BASE": f"ou=people,{BASE}",
        "OWL_SERVER_LDAP_ADMIN_VALUES": "owl-admins",
        "OWL_SERVER_LDAP_REGISTRY_ROLES": json.dumps(
            {"owl-publishers": {"team": "publisher"}, "owl-readers": {"team": "reader"}}
        ),
    }
    client = TestClient(create_app(load_settings(env), ldap_connection_factory=factory))
    client.post(
        "/api/v1/registries", headers=auth(ADMIN), json={"slug": "team", "visibility": "private"}
    )
    yield client
    client.close()


def ldap_login(client, user, password):
    return client.post("/api/v1/auth/login", json={"username": user, "password": password})


def test_ldap_login_creates_account_and_maps_groups(ldap_client):
    assert ldap_client.get("/api/v1/auth/config").json()["ldap"] == {"label": "Directory login"}
    result = ldap_login(ldap_client, "alice", "alice-secret-1")
    assert result.status_code == 200, result.text
    token = result.json()["token"]
    me = ldap_client.get("/api/v1/auth/me", headers=auth(token)).json()
    assert me["username"] == "alice" and me["is_admin"] is True
    assert me["memberships"] == [{"registry": "team", "role": "publisher"}]
    assert put(ldap_client, make_skill("by-ldap"), auth(token), registry="team").status_code == 201
    users = ldap_client.get("/api/v1/admin/users", headers=auth(ADMIN)).json()
    assert users[0]["provider"] == "ldap" and users[0]["email"] == "alice@corp.example"
    bob = ldap_login(ldap_client, "bob", "bob-secret-12").json()["token"]
    assert ldap_client.get("/api/v1/auth/me", headers=auth(bob)).json()["is_admin"] is False
    assert ldap_client.get("/r/team/api/v1/skills", headers=auth(bob)).status_code == 200
    assert put(ldap_client, make_skill("nope"), auth(bob), registry="team").status_code == 403


def test_ldap_wrong_unknown_and_empty_credentials(ldap_client, directory):
    _factory, calls = directory
    assert ldap_login(ldap_client, "alice", "wrong-password").status_code == 401
    assert ldap_login(ldap_client, "nobody", "whatever-123").status_code == 401
    before = len(calls)
    assert (
        ldap_login(ldap_client, "alice", "").status_code == 401
    )  # an empty password must never reach the server
    assert len(calls) == before
    assert ldap_login(ldap_client, "", "x" * 12).status_code == 401
    failed = ldap_client.get(
        "/api/v1/admin/audit?action=auth.login_failed", headers=auth(ADMIN)
    ).json()
    assert len(failed) >= 3 and "wrong-password" not in str(failed)


@pytest.mark.parametrize(
    "attack", ["*", "alice)(sAMAccountName=*", "*)(|(sAMAccountName=*", "alice\\00"]
)
def test_ldap_filter_injection_is_neutralised(ldap_client, attack):
    assert ldap_login(ldap_client, attack, "alice-secret-1").status_code == 401


def test_ldap_ambiguous_match_is_refused(ldap_client):
    assert ldap_login(ldap_client, "twin", "twin-secret-1").status_code == 401


def test_ldap_membership_follows_the_directory_on_every_login(ldap_client, directory):
    ldap_login(ldap_client, "bob", "bob-secret-12")
    assert ldap_client.get("/api/v1/registries/team/members", headers=auth(ADMIN)).json() == [
        {"username": "bob", "role": "reader"}
    ]
    # remove bob from the group in the directory: the next login removes the membership again
    server = directory[0]("cn=admin,dc=corp,dc=example", "admin-pw").server
    boot = Connection(
        server, user="cn=admin,dc=corp,dc=example", password="admin-pw", client_strategy=MOCK_SYNC
    )
    boot.strategy.remove_entry(f"cn=Bob B,ou=people,{BASE}")
    boot.strategy.add_entry(
        f"cn=Bob B,ou=people,{BASE}",
        {
            "userPassword": "bob-secret-12",
            "objectClass": "person",
            "sAMAccountName": "bob",
            "mail": "bob@corp.example",
            "memberOf": [],
        },
    )
    ldap_login(ldap_client, "bob", "bob-secret-12")
    assert ldap_client.get("/api/v1/registries/team/members", headers=auth(ADMIN)).json() == []


def test_local_accounts_take_precedence_and_are_never_hijacked(ldap_client):
    ldap_client.post(
        "/api/v1/admin/users", headers=auth(ADMIN), json={"username": "alice", "password": GOOD}
    )
    assert (
        ldap_login(ldap_client, "alice", "alice-secret-1").status_code == 401
    )  # directory password does not open the local account
    assert ldap_login(ldap_client, "alice", GOOD).status_code == 200


def test_disabled_ldap_user_is_refused_and_directory_outage_is_a_502(ldap_client, database_url):
    ldap_login(ldap_client, "bob", "bob-secret-12")
    ldap_client.patch("/api/v1/admin/users/bob", headers=auth(ADMIN), json={"active": False})
    assert ldap_login(ldap_client, "bob", "bob-secret-12").status_code == 403

    def broken(_user, _password):
        raise OSError("connection refused")

    outage = TestClient(
        create_app(
            load_settings(
                {
                    "OWL_SERVER_DATABASE_URL": database_url,
                    "OWL_SERVER_ADMIN_TOKEN": ADMIN,
                    "OWL_SERVER_LDAP_URL": "ldaps://x",
                    "OWL_SERVER_LDAP_BIND_DN": "cn=a",
                    "OWL_SERVER_LDAP_BIND_PASSWORD": "p",
                    "OWL_SERVER_LDAP_USER_BASE": "dc=x",
                }
            ),
            ldap_connection_factory=broken,
        )
    )
    response = ldap_login(outage, "alice", "x" * 12)
    assert (
        response.status_code == 502
        and "not reachable" in response.json()["detail"]
        and "refused" not in response.text
    )


# -- proxy authentication (Kerberos/SPNEGO, SAML, oauth2-proxy ... in front of OWL) -------------------
SECRET = "proxy-shared-secret-0123456789"


@pytest.fixture
def proxy_client(database_url):
    env = {
        "OWL_SERVER_DATABASE_URL": database_url,
        "OWL_SERVER_ADMIN_TOKEN": ADMIN,
        "OWL_SERVER_PROXY_AUTH": "true",
        "OWL_SERVER_PROXY_SECRET": SECRET,
        "OWL_SERVER_PROXY_ADMIN_VALUES": "EXAMPLE\\owl-admins",
        "OWL_SERVER_PROXY_REGISTRY_ROLES": json.dumps({"EXAMPLE\\owl-devs": {"team": "publisher"}}),
    }
    client = TestClient(create_app(load_settings(env)))
    client.post(
        "/api/v1/registries", headers=auth(ADMIN), json={"slug": "team", "visibility": "private"}
    )
    yield client
    client.close()


def via_proxy(user, groups="", secret=SECRET, **extra):
    headers = {
        "X-OWL-Proxy-Secret": secret,
        "X-Remote-User": user,
        "X-Remote-Groups": groups,
        **extra,
    }
    return headers


def test_proxy_headers_with_the_secret_log_the_user_in(proxy_client):
    h = via_proxy(
        "jdoe@EXAMPLE.COM",
        "EXAMPLE\\owl-devs,Domain Users",
        **{"X-Remote-Email": "jdoe@example.com"},
    )
    me = proxy_client.get("/api/v1/auth/me", headers=h).json()
    assert me["username"] == "jdoe@EXAMPLE.COM" and me["memberships"] == [
        {"registry": "team", "role": "publisher"}
    ]
    assert put(proxy_client, make_skill("by-kerberos"), h, registry="team").status_code == 201
    assert proxy_client.get("/api/v1/admin/users", headers=h).status_code == 403
    admin = via_proxy("boss@EXAMPLE.COM", "EXAMPLE\\owl-admins")
    assert proxy_client.get("/api/v1/admin/users", headers=admin).status_code == 200
    users = {
        u["username"]: u
        for u in proxy_client.get("/api/v1/admin/users", headers=auth(ADMIN)).json()
    }
    assert (
        users["jdoe@EXAMPLE.COM"]["provider"] == "proxy"
        and users["jdoe@EXAMPLE.COM"]["email"] == "jdoe@example.com"
    )


def test_forged_or_unsigned_proxy_headers_are_worthless(proxy_client):
    assert (
        proxy_client.get(
            "/api/v1/auth/me", headers=via_proxy("x", secret="wrong-secret-wrong-secret-12")
        ).status_code
        == 401
    )
    unsigned = {
        "X-Remote-User": "boss",
        "X-Remote-Groups": "EXAMPLE\\owl-admins",
    }  # a client trying to impersonate
    assert proxy_client.get("/api/v1/auth/me", headers=unsigned).json()["authenticated"] is False
    assert proxy_client.get("/api/v1/admin/users", headers=unsigned).status_code == 401
    assert (
        proxy_client.get("/api/v1/admin/users", headers={"X-OWL-Proxy-Secret": SECRET}).status_code
        == 401
    )  # secret, no user


def test_proxy_group_changes_apply_immediately_and_disabled_users_are_blocked(proxy_client):
    proxy_client.get("/api/v1/auth/me", headers=via_proxy("dev", "EXAMPLE\\owl-devs"))
    assert proxy_client.get("/api/v1/registries/team/members", headers=auth(ADMIN)).json() == [
        {"username": "dev", "role": "publisher"}
    ]
    proxy_client.get("/api/v1/auth/me", headers=via_proxy("dev", ""))  # group removed at the proxy
    assert proxy_client.get("/api/v1/registries/team/members", headers=auth(ADMIN)).json() == []
    proxy_client.patch("/api/v1/admin/users/dev", headers=auth(ADMIN), json={"active": False})
    assert proxy_client.get("/api/v1/auth/me", headers=via_proxy("dev")).status_code == 403


def test_proxy_never_takes_over_a_local_account(proxy_client):
    proxy_client.post(
        "/api/v1/admin/users", headers=auth(ADMIN), json={"username": "alice", "password": GOOD}
    )
    me = proxy_client.get("/api/v1/auth/me", headers=via_proxy("alice")).json()
    assert me["username"] == "alice@proxy"


# -- configuration validation ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "env, message",
    [
        ({"OWL_SERVER_LDAP_URL": "http://x"}, "ldaps:// or ldap://"),
        (
            {
                "OWL_SERVER_LDAP_URL": "ldap://x",
                "OWL_SERVER_LDAP_BIND_DN": "a",
                "OWL_SERVER_LDAP_BIND_PASSWORD": "b",
                "OWL_SERVER_LDAP_USER_BASE": "c",
            },
            "unencrypted",
        ),
        ({"OWL_SERVER_LDAP_URL": "ldaps://x"}, "LDAP needs"),
        (
            {
                "OWL_SERVER_LDAP_URL": "ldaps://x",
                "OWL_SERVER_LDAP_BIND_DN": "a",
                "OWL_SERVER_LDAP_BIND_PASSWORD": "b",
                "OWL_SERVER_LDAP_USER_BASE": "c",
                "OWL_SERVER_LDAP_USER_FILTER": "(uid=x)",
            },
            "{username}",
        ),
        ({"OWL_SERVER_PROXY_AUTH": "true"}, "PROXY_SECRET"),
        ({"OWL_SERVER_PROXY_AUTH": "true", "OWL_SERVER_PROXY_SECRET": "short"}, "24 characters"),
        ({"OWL_SERVER_OAUTH_CLIENT_ID": "x"}, "OAuth needs"),
        ({"OWL_SERVER_OAUTH_CLIENT_ID": "x", "OWL_SERVER_OAUTH_PRESET": "gitlab"}, "PRESET"),
        (
            {
                "OWL_SERVER_OIDC_ISSUER": "https://i",
                "OWL_SERVER_OIDC_CLIENT_ID": "c",
                "OWL_SERVER_OIDC_REDIRECT_URI": "https://r",
                "OWL_SERVER_OIDC_REGISTRY_ROLES": json.dumps({"g": {"team": "king"}}),
            },
            "reader/publisher/admin",
        ),
    ],
)
def test_provider_configuration_is_validated(env, message):
    with pytest.raises(ConfigError, match=message):
        load_settings({"OWL_SERVER_DATABASE_URL": "x", **env})


def test_ldap_start_tls_and_lab_override_are_accepted():
    base = {
        "OWL_SERVER_DATABASE_URL": "x",
        "OWL_SERVER_LDAP_BIND_DN": "a",
        "OWL_SERVER_LDAP_BIND_PASSWORD": "b",
        "OWL_SERVER_LDAP_USER_BASE": "c",
    }
    assert load_settings(
        {**base, "OWL_SERVER_LDAP_URL": "ldap://x", "OWL_SERVER_LDAP_START_TLS": "true"}
    ).ldap.start_tls
    assert load_settings(
        {**base, "OWL_SERVER_LDAP_URL": "ldap://x", "OWL_SERVER_LDAP_ALLOW_INSECURE": "true"}
    ).ldap
    assert (
        load_settings({"OWL_SERVER_DATABASE_URL": "x"}).open is None
        and load_settings({"OWL_SERVER_DATABASE_URL": "x"}).local_accounts
    )
