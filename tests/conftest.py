from __future__ import annotations

import os
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from owl.models import Skill
from sqlalchemy import text

from owl_server import db
from owl_server.app import create_app
from owl_server.config import load_settings

ADMIN = "bootstrap-admin-token-0123456789abcdef"
PG_URL = os.environ.get("OWL_SERVER_TEST_POSTGRES_URL")


def make_skill(name="alpha", author="alice", **kw) -> Skill:
    description = kw.pop("description", f"The {name} skill for testing")
    content = kw.pop(
        "content", f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nBody.\n"
    )
    return Skill(author=author, name=name, description=description, content=content, **kw)


@pytest.fixture
def database_url(tmp_path):
    if PG_URL:
        engine = db.make_engine(PG_URL)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
        return PG_URL
    return str(tmp_path / "server.sqlite3")


@pytest.fixture
def make_app(database_url) -> Callable[..., TestClient]:
    """Build an app (and a client) with the given environment overrides."""
    clients: list[TestClient] = []

    def build(**overrides: str) -> TestClient:
        env = {
            "OWL_SERVER_DATABASE_URL": database_url,
            "OWL_SERVER_ADMIN_TOKEN": ADMIN,
            "OWL_SERVER_LOGIN_RATE_PER_MINUTE": "1000",
        }
        env.update({f"OWL_SERVER_{k.upper()}": v for k, v in overrides.items()})
        client = TestClient(create_app(load_settings(env)))
        clients.append(client)
        return client

    yield build
    for c in clients:
        c.close()


@pytest.fixture
def client(make_app) -> TestClient:
    return make_app(mode="mixed")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers():
    return auth(ADMIN)


def put(client: TestClient, skill: Skill, headers, registry: str | None = None):
    prefix = f"/r/{registry}" if registry else ""
    return client.put(
        f"{prefix}/api/v1/skills/{skill.author}/{skill.name}", json=skill.to_dict(), headers=headers
    )
