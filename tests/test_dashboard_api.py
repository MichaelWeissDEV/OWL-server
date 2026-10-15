"""Endpoints the dashboard uses: importing, file preview, activity, registry details."""

from __future__ import annotations

import base64
import io
import zipfile

from tests.conftest import ADMIN, auth, make_skill, put

H = auth(ADMIN)
SKILL = "---\nname: pdf-tools\ndescription: Extract text from PDFs\ntags: [pdf, office]\nversion: 1.2.0\n---\n# PDF tools\n\nBody.\n"


def test_import_from_raw_skill_md(client):
    result = client.post(
        "/api/v1/skills/import", headers=H, json={"content": SKILL, "author": "Alice"}
    )
    assert result.status_code == 201, result.text
    body = result.json()
    assert (body["author"], body["name"], body["version"], body["tags"]) == (
        "alice",
        "pdf-tools",
        "1.2.0",
        ["office", "pdf"],
    )
    assert body["outcome"] == "created"
    again = client.post(
        "/api/v1/skills/import", headers=H, json={"content": SKILL, "author": "alice"}
    )
    assert again.status_code == 200 and again.json()["outcome"] == "unchanged"
    edited = client.post(
        "/api/v1/skills/import",
        headers=H,
        json={"content": SKILL.replace("Body.", "New body."), "author": "alice"},
    )
    assert edited.json()["outcome"] == "new-version"
    assert len(client.get("/api/v1/skills/alice/pdf-tools/versions", headers=H).json()) == 2


def test_import_defaults_overrides_files_and_errors(client):
    files = {"scripts/run.py": base64.b64encode(b"print(1)").decode()}
    ok = client.post(
        "/api/v1/skills/import",
        headers=H,
        json={"content": SKILL, "files": files, "overrides": {"version": "9.0.0", "tags": ["x"]}},
    )
    assert (
        ok.status_code == 201
        and ok.json()["version"] == "9.0.0"
        and ok.json()["author"] == "bootstrap-admin"
    )
    assert list(
        client.get("/api/v1/skills/bootstrap-admin/pdf-tools", headers=H).json()["files"]
    ) == ["scripts/run.py"]
    assert client.post("/api/v1/skills/import", headers=H, json={}).status_code == 422
    assert (
        client.post(
            "/api/v1/skills/import", headers=H, json={"content": "no frontmatter"}
        ).status_code
        == 422
    )
    broken = client.post(
        "/api/v1/skills/import", headers=H, json={"content": "---\nname: [unclosed\n---\nx"}
    )
    assert broken.status_code == 422 and "YAML" in broken.json()["detail"]
    bad_path = client.post(
        "/api/v1/skills/import", headers=H, json={"content": SKILL, "files": {"../evil": "aGk="}}
    )
    assert bad_path.status_code == 422
    assert (
        client.post("/api/v1/skills/import", json={"content": SKILL}).status_code == 401
    )  # needs a role


def make_zip(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def test_import_zip_reports_each_skill(client):
    archive = make_zip(
        {
            "pkg/good/SKILL.md": SKILL,
            "pkg/good/scripts/run.sh": "echo hi",
            "pkg/bad/SKILL.md": "no frontmatter at all",
        }
    )
    result = client.post(
        "/api/v1/import-zip",
        headers=H,
        files={"file": ("skills.zip", archive)},
        data={"author": "zed"},
    )
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["imported"] == 1 and report["invalid"] == 1
    by_name = {r["name"]: r for r in report["results"]}
    assert (
        by_name["pdf-tools"]["status"] == "created"
        and by_name["pdf-tools"]["ref"] == "zed/pdf-tools"
    )
    assert by_name["bad"]["status"] == "invalid" and by_name["bad"]["problems"]
    assert client.get("/api/v1/skills/zed/pdf-tools", headers=H).json()["files"].keys() == {
        "scripts/run.sh"
    }


def test_import_zip_rejects_hostile_archives(client):
    for members in ({"../evil/SKILL.md": SKILL}, {"/abs/SKILL.md": SKILL}):
        assert (
            client.post(
                "/api/v1/import-zip", headers=H, files={"file": ("x.zip", make_zip(members))}
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/v1/import-zip", headers=H, files={"file": ("x.zip", b"not a zip")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/import-zip",
            headers=H,
            files={"file": ("x.zip", make_zip({"readme.txt": "x"}))},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/skills", headers=H).json() == []  # nothing was stored


def test_file_listing_and_safe_preview(client):
    skill = make_skill(
        "viewer",
        files={
            "notes.md": b"# hello",
            "page.html": b"<script>alert(1)</script>",
            "blob.bin": bytes(range(256)),
        },
    )
    put(client, skill, H)
    listing = {
        f["path"]: f for f in client.get("/api/v1/skills/alice/viewer/files", headers=H).json()
    }
    assert set(listing) == {"SKILL.md", "skill.json", "notes.md", "page.html", "blob.bin"}
    assert (
        listing["notes.md"]["text"] is True
        and listing["blob.bin"]["text"] is False
        and len(listing["notes.md"]["sha256"]) == 64
    )
    md = client.get("/api/v1/skills/alice/viewer/files/notes.md", headers=H)
    assert md.text == "# hello" and md.headers["content-type"].startswith("text/plain")
    html = client.get("/api/v1/skills/alice/viewer/files/page.html", headers=H)
    assert (
        html.headers["content-type"].startswith("text/plain")
        and html.headers["x-content-type-options"] == "nosniff"
    )  # never rendered as HTML
    blob = client.get("/api/v1/skills/alice/viewer/files/blob.bin", headers=H)
    assert (
        blob.headers["content-type"] == "application/octet-stream"
        and "attachment" in blob.headers["content-disposition"]
    )
    assert (
        "name: viewer" in client.get("/api/v1/skills/alice/viewer/files/SKILL.md", headers=H).text
    )
    assert client.get("/api/v1/skills/alice/viewer/files/missing.txt", headers=H).status_code == 404
    assert (
        client.get("/api/v1/skills/alice/viewer/files/..%2f..%2fetc/passwd", headers=H).status_code
        == 404
    )


def test_file_endpoints_can_target_old_versions(client):
    put(client, make_skill("v", description="old", files={"a.txt": b"one"}), H)
    old = client.get("/api/v1/skills/alice/v", headers=H).json()["sha256"]
    put(client, make_skill("v", description="new", files={"a.txt": b"two"}), H)
    assert client.get(f"/api/v1/skills/alice/v/files/a.txt?version={old}", headers=H).text == "one"
    assert client.get("/api/v1/skills/alice/v/files/a.txt", headers=H).text == "two"


def test_activity_feed(client):
    put(client, make_skill("a", description="first"), H)
    put(client, make_skill("a", description="second"), H)
    put(client, make_skill("b"), H)
    feed = client.get("/api/v1/activity", headers=H).json()
    assert [(e["ref"], e["current"]) for e in feed] == [
        ("alice/b", True),
        ("alice/a", True),
        ("alice/a", False),
    ]
    assert feed[0]["by"] == "bootstrap:bootstrap-admin" and len(feed[0]["sha256"]) == 64
    assert len(client.get("/api/v1/activity?limit=1", headers=H).json()) == 1


def test_registry_detail(client):
    client.post(
        "/api/v1/registries",
        headers=H,
        json={"slug": "team", "name": "Team", "visibility": "private"},
    )
    detail = client.get("/api/v1/registries/team", headers=H).json()
    assert (
        detail["slug"] == "team" and detail["visibility"] == "private" and detail["role"] == "admin"
    )
    assert client.get("/api/v1/registries/team").status_code == 401
    assert client.get("/api/v1/registries/missing", headers=H).status_code == 404
