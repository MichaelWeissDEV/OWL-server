"""initial schema: registries, skills with immutable versions, users, tokens, audit

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(8), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(200)),
        sa.Column("password_hash", sa.Text),
        sa.Column("is_admin", sa.Boolean, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(300)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_login", sa.String(40)),
        sa.UniqueConstraint("provider", "subject", name="uq_user_subject"),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registry_id", sa.Integer, sa.ForeignKey("registries.id"), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("current_version_id", sa.Integer),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("registry_id", "author", "name", name="uq_skill_identity"),
    )
    op.create_index("ix_skills_registry_name", "skills", ["registry_id", "name"])
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("extra_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.UniqueConstraint("skill_id", "sha256", name="uq_version_hash"),
    )
    with op.batch_alter_table("skills") as batch:
        batch.create_foreign_key(
            "fk_skill_current_version", "skill_versions", ["current_version_id"], ["id"]
        )
    op.create_table(
        "version_labels",
        sa.Column("version_id", sa.Integer, sa.ForeignKey("skill_versions.id"), primary_key=True),
        sa.Column("kind", sa.String(8), primary_key=True),
        sa.Column("value", sa.String(128), primary_key=True),
    )
    op.create_index("ix_version_labels_value", "version_labels", ["kind", "value"])
    op.create_table(
        "version_files",
        sa.Column("version_id", sa.Integer, sa.ForeignKey("skill_versions.id"), primary_key=True),
        sa.Column("path", sa.String(512), primary_key=True),
        sa.Column("data", sa.LargeBinary, nullable=False),
    )
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registry_id", sa.Integer, sa.ForeignKey("registries.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("registry_id", "name", name="uq_collection_name"),
    )
    op.create_table(
        "collection_skills",
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("collections.id"), primary_key=True),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skills.id"), primary_key=True),
    )
    op.create_table(
        "memberships",
        sa.Column("registry_id", sa.Integer, sa.ForeignKey("registries.id"), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(10), nullable=False),
    )
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("registry_id", sa.Integer, sa.ForeignKey("registries.id")),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40)),
        sa.Column("revoked_at", sa.String(40)),
        sa.Column("last_used_at", sa.String(40)),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(300), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_events_at", "audit_events", ["at"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_table(
        "oidc_states",
        sa.Column("state", sa.String(64), primary_key=True),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("verifier", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "oidc_states",
        "audit_events",
        "api_tokens",
        "memberships",
        "collection_skills",
        "collections",
        "version_files",
        "version_labels",
    ):
        op.drop_table(table)
    with op.batch_alter_table("skills") as batch:
        batch.drop_constraint("fk_skill_current_version", type_="foreignkey")
    for table in ("skill_versions", "skills", "users", "registries"):
        op.drop_table(table)
