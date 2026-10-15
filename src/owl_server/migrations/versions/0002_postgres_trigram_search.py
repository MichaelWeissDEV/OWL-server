"""PostgreSQL only: trigram indexes that speed up substring search (best effort)

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_skills_name_trgm", "skills", "name"),
    ("ix_versions_description_trgm", "skill_versions", "description"),
    ("ix_versions_content_trgm", "skill_versions", "content"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    try:  # the role may not be allowed to create extensions: search then simply scans
        with bind.begin_nested():
            op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            for name, table, column in INDEXES:
                op.execute(
                    f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin (lower({column}) gin_trgm_ops)"
                )
    except sa.exc.DBAPIError:
        pass


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for name, _table, _column in INDEXES:
            op.execute(f"DROP INDEX IF EXISTS {name}")
