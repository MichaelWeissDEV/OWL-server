"""PostgreSQL data model. Skills are stored as immutable, hash-addressed *versions*."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Base(DeclarativeBase):
    pass


class Registry(Base):
    """A named collection of skills with its own visibility and members."""

    __tablename__ = "registries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(8), default="private")  # public | private
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("registry_id", "author", "name", name="uq_skill_identity"),
        Index("ix_skills_registry_name", "registry_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry_id: Mapped[int] = mapped_column(ForeignKey("registries.id"))
    author: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(64))
    #: the newest version; set after the first version row exists
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("skill_versions.id", use_alter=True, name="fk_skill_current_version"),
        nullable=True,
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)

    versions: Mapped[list[SkillVersion]] = relationship(
        back_populates="skill",
        foreign_keys="SkillVersion.skill_id",
        cascade="all, delete-orphan",
        order_by="SkillVersion.id",
    )


class SkillVersion(Base):
    """One immutable revision of a skill, identified by its content hash."""

    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "sha256", name="uq_version_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    created_by: Mapped[str] = mapped_column(String(200), default="")

    skill: Mapped[Skill] = relationship(back_populates="versions", foreign_keys=[skill_id])
    labels: Mapped[list[VersionLabel]] = relationship(cascade="all, delete-orphan")
    files: Mapped[list[VersionFile]] = relationship(cascade="all, delete-orphan")


class VersionLabel(Base):
    __tablename__ = "version_labels"
    __table_args__ = (Index("ix_version_labels_value", "kind", "value"),)

    version_id: Mapped[int] = mapped_column(ForeignKey("skill_versions.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)  # tag | topic
    value: Mapped[str] = mapped_column(String(128), primary_key=True)


class VersionFile(Base):
    __tablename__ = "version_files"

    version_id: Mapped[int] = mapped_column(ForeignKey("skill_versions.id"), primary_key=True)
    path: Mapped[str] = mapped_column(String(512), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("registry_id", "name", name="uq_collection_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry_id: Mapped[int] = mapped_column(ForeignKey("registries.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class CollectionSkill(Base):
    __tablename__ = "collection_skills"

    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), primary_key=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)  # None for OIDC users
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[str] = mapped_column(String(16), default="local")  # local | oidc
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    last_login: Mapped[str | None] = mapped_column(String(40), nullable=True)
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_user_subject"),)


class Membership(Base):
    """A user's role in one registry: reader, publisher or admin."""

    __tablename__ = "memberships"

    registry_id: Mapped[int] = mapped_column(ForeignKey("registries.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(10))


class ApiToken(Base):
    """API tokens and login sessions. Only a SHA-256 of the secret is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), default="api")  # api | session
    name: Mapped[str] = mapped_column(String(100), default="")
    prefix: Mapped[str] = mapped_column(String(12))  # shown in listings to identify a token
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(10), default="reader")  # cap for the token
    registry_id: Mapped[int | None] = mapped_column(ForeignKey("registries.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_used_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[str] = mapped_column(String(40), default=now, index=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(300), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")


class OidcState(Base):
    """Short-lived data of a running OIDC login (state, nonce, PKCE verifier)."""

    __tablename__ = "oidc_states"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    expires_at: Mapped[str] = mapped_column(String(40))


class ServerSetting(Base):
    """Key/value settings changed at run time from the dashboard (for example ``secured``)."""

    __tablename__ = "server_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
