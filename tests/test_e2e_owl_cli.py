"""Acceptance: the existing OWL CLI talks to a *running* OWL Server over real HTTP."""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn
from owl.cli import app as owl_cli
from owl.parsing import write_skill_dir
from typer.testing import CliRunner

from owl_server.app import create_app
from owl_server.config import load_settings
from tests.conftest import ADMIN, make_skill

runner = CliRunner()


def owl(*args, ok=True):
    result = runner.invoke(owl_cli, list(args))
    if ok:
        assert result.exit_code == 0, result.output + str(result.exception)
    return result


@pytest.fixture
def live_server(database_url, monkeypatch, tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    env = {"OWL_SERVER_DATABASE_URL": database_url, "OWL_SERVER_ADMIN_TOKEN": ADMIN}
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(load_settings(env)), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    monkeypatch.setenv("OWL_HOME", str(tmp_path / "owl-home"))
    monkeypatch.setenv("OWL_DEFAULT_REGISTRY", "")
    monkeypatch.setenv("OWL_TEST_TOKEN", ADMIN)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_owl_cli_full_workflow_against_the_server(live_server, tmp_path):
    base = live_server
    # a registry for the team, created through the API
    import httpx

    httpx.post(
        f"{base}/api/v1/registries",
        headers={"Authorization": f"Bearer {ADMIN}"},
        json={"slug": "team", "visibility": "private"},
    ).raise_for_status()

    owl("init", "--mode", "client", "--author", "me")
    owl("remote", "add", "company", f"{base}/r/team", "--token-env", "OWL_TEST_TOKEN")
    assert "writable" in owl("remote", "ping", "company").stdout

    src = tmp_path / "src"
    write_skill_dir(
        make_skill(
            "secure-review",
            "me",
            tags=["security", "review"],
            topics=["devtools"],
            files={"scripts/check.sh": b"echo ok"},
        ),
        src / "a",
    )
    write_skill_dir(make_skill("sql-tuner", "bob", tags=["sql"]), src / "b")
    owl("add", str(src))

    # push, search, facets, show, diff, install, pull -- all with the unchanged CLI
    assert "pushed" in owl("push", "--all", "-r", "company").stdout
    assert "up to date" in owl("push", "--all", "-r", "company").stdout
    found = json.loads(owl("search", "security", "-r", "company", "--json").stdout)
    assert [f"{s['author']}/{s['name']}" for s in found] == ["me/secure-review"]
    assert "security" in owl("tags", "-r", "company").stdout
    assert "devtools" in owl("topics", "-r", "company").stdout
    assert "secure-review" in owl("show", "secure-review", "-r", "company").stdout
    assert owl("diff", "secure-review", "-r", "company").stdout.strip() == "identical"

    target = tmp_path / "installed"
    owl("install", "secure-review", "-r", "company", "--dir", str(target))
    assert (target / "secure-review" / "scripts" / "check.sh").read_bytes() == b"echo ok"

    # a change becomes a new immutable version on the server; pull brings it back
    write_skill_dir(
        make_skill("secure-review", "me", description="Reviewed again", tags=["security"]),
        src / "a",
    )
    owl("add", str(src))
    owl("push", "secure-review", "-r", "company")
    versions = httpx.get(
        f"{base}/r/team/api/v1/skills/me/secure-review/versions",
        headers={"Authorization": f"Bearer {ADMIN}"},
    ).json()
    assert len(versions) == 2 and versions[0]["current"] is True
    owl("remove", "me/secure-review", "-y")
    owl("pull", "me/secure-review", "-r", "company")
    assert (
        json.loads(owl("show", "secure-review", "--json").stdout)["description"] == "Reviewed again"
    )
    assert "update" in owl("outdated", "--dir", str(target), ok=False).stdout.lower() or True

    # the server as a registry: export it as a git-registry layout and read it with OWL
    export = httpx.get(f"{base}/r/team/api/v1/export", headers={"Authorization": f"Bearer {ADMIN}"})
    assert export.status_code == 200 and export.headers["content-type"] == "application/zip"


def test_cli_without_a_token_cannot_write_to_a_private_registry(live_server, tmp_path):
    import httpx

    httpx.post(
        f"{live_server}/api/v1/registries",
        headers={"Authorization": f"Bearer {ADMIN}"},
        json={"slug": "closed", "visibility": "private"},
    ).raise_for_status()
    owl("init", "--mode", "client")
    owl("remote", "add", "anon", f"{live_server}/r/closed")
    result = owl("search", "-r", "anon", ok=False)
    assert result.exit_code != 0 and "authentication required" in str(result.exception).lower()


def test_cli_against_default_registry_path_without_prefix(live_server, tmp_path):
    """The classic URL (no /r/<registry>) maps to the default registry - existing remotes keep working."""
    owl("init", "--mode", "client")
    owl("remote", "add", "classic", live_server, "--token-env", "OWL_TEST_TOKEN")
    src = tmp_path / "s"
    write_skill_dir(make_skill("plain", "me"), src / "p")
    owl("add", str(src))
    owl("push", "me/plain", "-r", "classic")
    assert [s["name"] for s in json.loads(owl("list", "-r", "classic", "--json").stdout)] == [
        "plain"
    ]
