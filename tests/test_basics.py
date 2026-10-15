"""Configuration, migrations, health, and compatibility with OWL's own client."""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from owl.models import AmbiguousRef, InvalidSkill, NotFound, SearchQuery
from owl.stores.remote import RemoteStore
from sqlalchemy import inspect

from owl_server import db
from owl_server.config import ConfigError, load_settings
from owl_server.models import Base
from tests.conftest import ADMIN, auth, make_skill, put


# -- configuration ----------------------------------------------------------------------------
def test_config_requires_database_and_validates():
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_settings({})
    base = {"OWL_SERVER_DATABASE_URL": "postgresql://u@h/d"}
    with pytest.raises(ConfigError, match="MODE"):
        load_settings({**base, "OWL_SERVER_MODE": "open"})
    with pytest.raises(ConfigError, match="at least 24"):
        load_settings({**base, "OWL_SERVER_ADMIN_TOKEN": "short"})
    with pytest.raises(ConfigError, match="https"):
        load_settings(
            {
                **base,
                "OWL_SERVER_OIDC_ISSUER": "http://idp",
                "OWL_SERVER_OIDC_CLIENT_ID": "x",
                "OWL_SERVER_OIDC_REDIRECT_URI": "https://app/cb",
            }
        )
    with pytest.raises(ConfigError, match="CLIENT_ID"):
        load_settings({**base, "OWL_SERVER_OIDC_ISSUER": "https://idp"})
    settings = load_settings(
        {**base, "OWL_SERVER_MODE": "PUBLIC", "OWL_SERVER_LOCAL_ACCOUNTS": "yes"}
    )
    assert settings.mode == "public" and settings.local_accounts and settings.oidc is None


def test_secrets_can_come_from_files(tmp_path):
    secret = tmp_path / "token"
    secret.write_text("a-very-long-secret-token-from-a-file-123\n")
    settings = load_settings(
        {"OWL_SERVER_DATABASE_URL": "x", "OWL_SERVER_ADMIN_TOKEN_FILE": str(secret)}
    )
    assert settings.admin_token == "a-very-long-secret-token-from-a-file-123"
    with pytest.raises(ConfigError, match="cannot read"):
        load_settings(
            {
                "OWL_SERVER_DATABASE_URL": "x",
                "OWL_SERVER_ADMIN_TOKEN_FILE": str(tmp_path / "missing"),
            }
        )


def test_url_normalisation():
    assert db.normalize_url("postgresql://u@h/d") == "postgresql+psycopg://u@h/d"
    assert db.normalize_url("postgres://u@h/d") == "postgresql+psycopg://u@h/d"
    assert db.normalize_url("/tmp/x.db").startswith("sqlite:////")


# -- migrations ---------------------------------------------------------------------------------
def test_migrated_schema_matches_the_models(database_url):
    db.upgrade(database_url)
    engine = db.make_engine(database_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    diff = [
        d for d in diff if not (d[0] == "remove_index" and d[1].name.endswith("_trgm"))
    ]  # PostgreSQL-only
    assert diff == [], diff
    assert {"registries", "skills", "skill_versions", "users", "api_tokens", "audit_events"} <= set(
        inspect(engine).get_table_names()
    )
    db.upgrade(database_url)  # idempotent
    assert db.current_revision(engine) == db.head_revision(database_url)


def test_downgrade_and_upgrade_roundtrip(database_url):
    from alembic import command

    db.upgrade(database_url)
    cfg = db.alembic_config(database_url)
    command.downgrade(cfg, "base")
    engine = db.make_engine(database_url)
    assert "skills" not in inspect(engine).get_table_names()
    db.upgrade(database_url)
    assert "skills" in inspect(db.make_engine(database_url)).get_table_names()


def test_health_and_ready(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"


def test_ready_reports_pending_migrations(make_app, database_url):
    client = make_app()
    from alembic import command

    command.downgrade(db.alembic_config(database_url), "base")
    response = client.get("/api/v1/ready")
    assert response.status_code == 503 and response.json()["status"] == "not ready"
    assert client.get("/api/v1/health").status_code == 200  # liveness is independent


# -- compatibility: OWL's own RemoteStore talks to this server --------------------------------------
@pytest.fixture
def remote(client):
    return RemoteStore("http://testserver", ADMIN, label="srv", client=client)


def test_roundtrip_preserves_hash_files_and_metadata(remote):
    skill = make_skill(
        "pdf-tools",
        "alice",
        tags=["pdf", "docs"],
        topics=["office"],
        version="1.2.0",
        files={"scripts/run.py": b"print(1)", "data.bin": bytes(range(256))},
        extra={"license": "MIT"},
    )
    stored = remote.upsert(skill)
    assert stored.sha256 == skill.sha256
    got = remote.get("alice", "pdf-tools")
    assert got is not None and got.sha256 == skill.sha256 and got.files == skill.files
    assert (
        got.extra == {"license": "MIT"} and got.tags == ["docs", "pdf"] and got.topics == ["office"]
    )


def test_search_semantics_match_owl(remote):
    for s in (
        make_skill("git-helper", "alice", tags=["git", "vcs"], topics=["devtools"]),
        make_skill("sql-tuner", "bob", tags=["sql", "postgres"]),
        make_skill("docs-writer", "alice", tags=["docs"], topics=["devtools", "writing"]),
    ):
        remote.upsert(s)

    def refs(**kw):
        return [s.ref for s in remote.search(SearchQuery(**kw))]

    assert refs() == ["alice/docs-writer", "alice/git-helper", "bob/sql-tuner"]
    assert refs(author="ALICE") == ["alice/docs-writer", "alice/git-helper"]
    assert refs(tags=["sql", "postgres"]) == ["bob/sql-tuner"] and refs(tags=["sql", "git"]) == []
    assert refs(topics=["devtools"]) == ["alice/docs-writer", "alice/git-helper"]
    assert refs(text="TUNER") == ["bob/sql-tuner"] and refs(text="postgres") == ["bob/sql-tuner"]
    assert refs(text="100%") == [] and refs(text="zzz") == []
    assert refs(limit=1, offset=1) == ["alice/git-helper"]
    assert remote.facets("author") == [("alice", 2), ("bob", 1)]
    assert dict(remote.facets("topic"))["devtools"] == 2


def test_relevance_prefers_name_matches(remote):
    remote.upsert(make_skill("aaa", description="mentions widget here"))
    remote.upsert(make_skill("widget-maker", description="makes things"))
    assert [s.name for s in remote.search(SearchQuery(text="widget"))] == ["widget-maker", "aaa"]


def test_resolution_delete_and_listing(remote):
    remote.upsert(make_skill("shared", "alice"))
    remote.upsert(make_skill("shared", "bob"))  # the server allows shared names across authors
    remote.upsert(make_skill("unique", "alice"))
    assert remote.resolve("unique") == ("alice", "unique")
    with pytest.raises(AmbiguousRef):
        remote.resolve("shared")
    with pytest.raises(NotFound):
        remote.resolve("missing")
    for i in range(7):
        remote.upsert(make_skill(f"skill-{i}"))
    assert len(remote.list()) == 10
    assert remote.delete("alice", "unique") is True and remote.delete("alice", "unique") is False


def test_invalid_uploads_are_rejected(remote, client, admin_headers):
    from owl.models import OwlError

    with pytest.raises((OwlError, InvalidSkill)):
        remote.upsert(make_skill("Bad_Name"))
    body = make_skill("x").to_dict()
    assert (
        client.put("/api/v1/skills/alice/other", json=body, headers=admin_headers).status_code
        == 422
    )
    body["files"] = {"../evil": "aGk="}
    assert client.put("/api/v1/skills/alice/x", json=body, headers=admin_headers).status_code == 422
    body["files"] = {"SKILL.md": "aGk="}  # reserved name
    assert client.put("/api/v1/skills/alice/x", json=body, headers=admin_headers).status_code == 422
    assert (
        client.put(
            "/api/v1/skills/alice/x", json={"nonsense": 1}, headers=admin_headers
        ).status_code
        == 422
    )


def test_info_endpoint_matches_what_owl_expects(client, admin_headers):
    put(client, make_skill("one"), admin_headers)
    info = client.get("/api/v1/info", headers=admin_headers).json()
    assert info["name"] == "owl" and info["server"] == "owl-server" and info["skills"] == 1
    assert info["writable"] is True and info["private"] is True and info["role"] == "admin"
    assert auth(ADMIN)["Authorization"].startswith("Bearer ")
