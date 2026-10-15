"""Immutable versions, ETags, registries, roles and the public/private/mixed modes."""

from __future__ import annotations

import io
import zipfile

import pytest

from tests.conftest import ADMIN, auth, make_skill, put


def create_registry(client, slug, visibility="private", headers=None):
    return client.post(
        "/api/v1/registries",
        json={"slug": slug, "visibility": visibility},
        headers=headers or auth(ADMIN),
    )


def make_user_token(client, make_app_headers, username, role, registry):
    """An admin creates a service token limited to one registry."""
    return client.post(
        "/api/v1/admin/tokens",
        headers=make_app_headers,
        json={"registry": registry, "role": role, "name": username},
    ).json()["token"]


# -- versions ---------------------------------------------------------------------------------
def test_changes_create_new_immutable_versions(client, admin_headers):
    assert (
        put(client, make_skill("v", description="one", version="1.0.0"), admin_headers).status_code
        == 201
    )
    assert (
        put(client, make_skill("v", description="one", version="1.0.0"), admin_headers).status_code
        == 200
    )
    put(client, make_skill("v", description="two", version="2.0.0"), admin_headers)
    versions = client.get("/api/v1/skills/alice/v/versions", headers=admin_headers).json()
    assert [(v["version"], v["current"]) for v in versions] == [("2.0.0", True), ("1.0.0", False)]
    old_sha = versions[1]["sha256"]
    old = client.get(f"/api/v1/skills/alice/v/versions/{old_sha}", headers=admin_headers).json()
    assert old["description"] == "one"  # the old version is still intact
    assert (
        client.get("/api/v1/skills/alice/v", headers=admin_headers).json()["description"] == "two"
    )
    assert (
        client.get(f"/api/v1/skills/alice/v?version={old_sha}", headers=admin_headers).json()[
            "version"
        ]
        == "1.0.0"
    )
    assert (
        client.get("/api/v1/skills/alice/v/versions/" + "0" * 64, headers=admin_headers).status_code
        == 404
    )
    # pushing the old content again makes it current (rollback) without duplicating the version
    put(client, make_skill("v", description="one", version="1.0.0"), admin_headers)
    versions = client.get("/api/v1/skills/alice/v/versions", headers=admin_headers).json()
    assert len(versions) == 2 and next(v for v in versions if v["current"])["version"] == "1.0.0"


def test_etag_conditional_requests_and_head(client, admin_headers):
    put(client, make_skill("e"), admin_headers)
    first = client.get("/api/v1/skills/alice/e", headers=admin_headers)
    etag = first.headers["etag"]
    assert etag == f'"{first.json()["sha256"]}"'
    cached = client.get("/api/v1/skills/alice/e", headers={**admin_headers, "If-None-Match": etag})
    assert cached.status_code == 304 and cached.content == b""
    head = client.head("/api/v1/skills/alice/e", headers=admin_headers)
    assert head.status_code == 200 and head.headers["etag"] == etag and head.content == b""
    put(client, make_skill("e", description="changed"), admin_headers)
    assert (
        client.get(
            "/api/v1/skills/alice/e", headers={**admin_headers, "If-None-Match": etag}
        ).status_code
        == 200
    )


def test_download_zip_and_export_as_git_registry_layout(client, admin_headers):
    put(client, make_skill("z", files={"scripts/a.sh": b"echo"}), admin_headers)
    zipped = client.get("/api/v1/skills/alice/z/download", headers=admin_headers)
    assert zipped.headers["content-type"] == "application/zip"
    assert sorted(zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()) == [
        "z/SKILL.md",
        "z/scripts/a.sh",
        "z/skill.json",
    ]
    export = client.get("/api/v1/export", headers=admin_headers)
    names = zipfile.ZipFile(io.BytesIO(export.content)).namelist()
    assert {
        "registry.json",
        "index.json",
        "INDEX.md",
        "skills/z/SKILL.md",
        "skills/z/skill.json",
    } <= set(names)


def test_delete_stats_index_and_collections(client, admin_headers):
    for n in ("a-skill", "b-skill"):
        put(client, make_skill(n, tags=["t"]), admin_headers)
    assert client.get("/api/v1/stats", headers=admin_headers).json()["skills"] == 2
    index = client.get("/api/v1/index", headers=admin_headers).json()
    assert index["count"] == 2 and all(len(s["sha256"]) == 64 for s in index["skills"])
    assert (
        client.post("/api/v1/collections", json={"name": "c"}, headers=admin_headers).status_code
        == 201
    )
    assert (
        client.post("/api/v1/collections", json={"name": "c"}, headers=admin_headers).status_code
        == 409
    )
    assert client.put(
        "/api/v1/collections/c/skills/alice/a-skill", headers=admin_headers
    ).json() == {"added": True}
    assert (
        client.put("/api/v1/collections/c/skills/alice/nope", headers=admin_headers).status_code
        == 404
    )
    assert client.get("/api/v1/collections/c", headers=admin_headers).json()["skills"] == [
        "alice/a-skill"
    ]
    assert client.get("/api/v1/collections", headers=admin_headers).json()[0]["skills"] == 1
    assert (
        client.delete("/api/v1/skills/alice/a-skill", headers=admin_headers).status_code == 200
    )  # also drops membership
    assert client.get("/api/v1/collections/c", headers=admin_headers).json()["skills"] == []
    assert client.get("/api/v1/skills/alice/a-skill", headers=admin_headers).status_code == 404
    assert client.delete("/api/v1/collections/c", headers=admin_headers).status_code == 200


# -- registries and roles ---------------------------------------------------------------------------
def test_private_registry_is_invisible_without_access(client, admin_headers):
    assert create_registry(client, "secret", "private").status_code == 201
    put(client, make_skill("hidden"), admin_headers, registry="secret")
    # anonymous: asked to authenticate; the response does not reveal whether it exists
    assert client.get("/r/secret/api/v1/skills").status_code == 401
    assert client.get("/r/nonexistent/api/v1/skills").status_code == 401
    assert client.get("/r/secret/api/v1/skills/alice/hidden").status_code == 401
    assert client.get("/api/v1/registries").json() == []  # nothing public
    # a token for another registry learns nothing either
    create_registry(client, "other", "private")
    other = make_user_token(client, admin_headers, "x", "admin", "other")
    assert client.get("/r/secret/api/v1/skills", headers=auth(other)).status_code == 404
    assert (
        client.get("/r/secret/api/v1/skills/alice/hidden", headers=auth(other)).status_code == 404
    )
    assert (
        client.get("/r/nonexistent/api/v1/skills", headers=auth(other)).status_code == 404
    )  # same answer
    assert [r["slug"] for r in client.get("/api/v1/registries", headers=auth(other)).json()] == [
        "other"
    ]
    # the skill never shows up in another registry's search or facets
    assert client.get("/r/other/api/v1/skills", headers=auth(other)).json() == []
    assert client.get("/r/other/api/v1/skills/alice/hidden", headers=auth(other)).status_code == 404


def test_role_matrix(client, admin_headers):
    create_registry(client, "team", "private")
    put(client, make_skill("existing"), admin_headers, registry="team")
    tokens = {
        r: make_user_token(client, admin_headers, r, r, "team")
        for r in ("reader", "publisher", "admin")
    }
    base = "/r/team/api/v1"
    new = make_skill("new-one").to_dict()
    # reader: read yes, write no (403 = authenticated but not allowed)
    reader = auth(tokens["reader"])
    assert client.get(f"{base}/skills", headers=reader).status_code == 200
    assert client.put(f"{base}/skills/alice/new-one", json=new, headers=reader).status_code == 403
    assert client.delete(f"{base}/skills/alice/existing", headers=reader).status_code == 403
    assert client.post(f"{base}/collections", json={"name": "c"}, headers=reader).status_code == 403
    # publisher: can publish and delete skills, but not administer the registry
    publisher = auth(tokens["publisher"])
    assert (
        client.put(f"{base}/skills/alice/new-one", json=new, headers=publisher).status_code == 201
    )
    assert (
        client.patch("/api/v1/registries/team", json={"name": "X"}, headers=publisher).status_code
        == 403
    )
    assert client.get("/api/v1/registries/team/members", headers=publisher).status_code == 403
    assert client.delete(f"{base}/skills/alice/new-one", headers=publisher).status_code == 200
    # registry admin: may rename, but not change visibility or create registries
    radmin = auth(tokens["admin"])
    assert (
        client.patch("/api/v1/registries/team", json={"name": "Team"}, headers=radmin).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/registries/team", json={"visibility": "public"}, headers=radmin
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/registries", json={"slug": "nope"}, headers=radmin).status_code == 403
    )
    assert client.get("/api/v1/admin/users", headers=radmin).status_code == 403
    # a service token is limited to its registry
    assert (
        client.get("/api/v1/skills", headers=reader).status_code == 404
    )  # the default registry is not theirs


def test_public_registry_readable_by_all_writable_only_with_rights(client, admin_headers):
    create_registry(client, "open", "public")
    put(client, make_skill("shared"), admin_headers, registry="open")
    assert client.get("/r/open/api/v1/skills").json()[0]["name"] == "shared"  # anonymous read
    assert client.get("/r/open/api/v1/skills/alice/shared").status_code == 200
    assert client.get("/r/open/api/v1/info").json()["writable"] is False
    assert put(client, make_skill("x"), {}, registry="open").status_code == 401
    assert put(client, make_skill("x"), auth("owl_invalid"), registry="open").status_code == 401
    assert [r["slug"] for r in client.get("/api/v1/registries").json()] == ["open"]
    assert client.get("/api/v1/skills").status_code == 401  # the default registry is private


def test_server_modes_override_registry_visibility(make_app):
    public = make_app(mode="public")
    assert (
        public.post(
            "/api/v1/registries", json={"slug": "p", "visibility": "private"}, headers=auth(ADMIN)
        ).status_code
        == 422
    )
    assert (
        public.get("/api/v1/skills").status_code == 200
    )  # the default registry is public in public mode
    assert (
        public.put("/api/v1/skills/alice/x", json=make_skill("x").to_dict()).status_code == 401
    )  # writes still need rights

    private = make_app(mode="private")
    assert (
        private.post(
            "/api/v1/registries", json={"slug": "p", "visibility": "public"}, headers=auth(ADMIN)
        ).status_code
        == 422
    )
    assert private.get("/api/v1/skills").status_code == 401


def test_changing_visibility_is_a_server_admin_action(client, admin_headers):
    create_registry(client, "flip", "private")
    put(client, make_skill("s"), admin_headers, registry="flip")
    assert client.get("/r/flip/api/v1/skills").status_code == 401
    assert (
        client.patch(
            "/api/v1/registries/flip", json={"visibility": "public"}, headers=admin_headers
        ).status_code
        == 200
    )
    assert client.get("/r/flip/api/v1/skills").status_code == 200
    client.patch("/api/v1/registries/flip", json={"visibility": "private"}, headers=admin_headers)
    assert client.get("/r/flip/api/v1/skills").status_code == 401


def test_registry_lifecycle(client, admin_headers):
    assert create_registry(client, "Bad Slug").status_code == 422
    assert create_registry(client, "life").status_code == 201
    assert create_registry(client, "life").status_code == 409
    put(client, make_skill("s"), admin_headers, registry="life")
    assert (
        client.delete("/api/v1/registries/life", headers=admin_headers).status_code == 409
    )  # not empty
    assert (
        client.delete("/api/v1/registries/life?force=true", headers=admin_headers).status_code
        == 200
    )
    assert client.get("/r/life/api/v1/skills", headers=admin_headers).status_code == 404
    assert client.delete("/api/v1/registries/default", headers=admin_headers).status_code == 409


def test_same_skill_in_two_registries_is_independent(client, admin_headers):
    create_registry(client, "a")
    create_registry(client, "b")
    put(client, make_skill("same", description="in a"), admin_headers, registry="a")
    put(client, make_skill("same", description="in b"), admin_headers, registry="b")
    assert (
        client.get("/r/a/api/v1/skills/alice/same", headers=admin_headers).json()["description"]
        == "in a"
    )
    assert (
        client.get("/r/b/api/v1/skills/alice/same", headers=admin_headers).json()["description"]
        == "in b"
    )
    client.delete("/r/a/api/v1/skills/alice/same", headers=admin_headers)
    assert client.get("/r/b/api/v1/skills/alice/same", headers=admin_headers).status_code == 200


def test_bad_tokens_and_headers(client):
    assert client.get("/api/v1/skills", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/skills", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/api/v1/skills", headers=auth("x" * 40)).status_code == 401


def test_request_body_limit(make_app):
    client = make_app(max_body_mb="1")
    big = make_skill("big", files={"blob.bin": b"x" * (2 * 1024 * 1024)})
    assert put(client, big, auth(ADMIN)).status_code == 413
    chunked = client.put(
        "/api/v1/skills/alice/big", content=(b"x" * 1024 for _ in range(1500)), headers=auth(ADMIN)
    )  # no Content-Length: limited while streaming
    assert chunked.status_code == 413
    assert put(client, make_skill("ok"), auth(ADMIN)).status_code == 201


def test_security_headers_and_no_secret_leaks(client, admin_headers):
    response = client.get("/api/v1/health")
    assert (
        response.headers["x-content-type-options"] == "nosniff"
        and response.headers["x-frame-options"] == "DENY"
    )
    put(client, make_skill("a"), admin_headers)
    audit = client.get("/api/v1/admin/audit", headers=admin_headers).json()
    assert audit and ADMIN not in str(audit)
    assert any(
        e["action"] == "skill.created" and e["actor"] == "bootstrap:bootstrap-admin" for e in audit
    )


@pytest.mark.parametrize(
    "path", ["/api/v1/admin/users", "/api/v1/admin/tokens", "/api/v1/admin/audit"]
)
def test_admin_endpoints_need_admin(client, path):
    assert client.get(path).status_code == 401
