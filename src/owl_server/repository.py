"""Skills of one registry: storage, versions and search, on top of OWL's core model.

The data model, content hashing and validation come from the ``owl`` package, so the server and the
CLI can never disagree about what a skill is or what its hash is.
"""

from __future__ import annotations

import json
from typing import Any

from owl.models import InvalidSkill, SearchQuery, Skill, SkillSummary, validate_skill
from sqlalchemy import case, delete, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from owl_server import models as m

FACETS = ("author", "tag", "topic")


class IntegrityProblem(RuntimeError):
    """Stored data no longer matches its recorded hash."""


def _to_skill(row: m.Skill, version: m.SkillVersion) -> Skill:
    skill = Skill(
        author=row.author,
        name=row.name,
        version=version.version,
        description=version.description,
        tags=[label.value for label in version.labels if label.kind == "tag"],
        topics=[label.value for label in version.labels if label.kind == "topic"],
        content=version.content,
        extra=json.loads(version.extra_json),
        files={f.path: bytes(f.data) for f in version.files},
        created_at=row.created_at,
        updated_at=version.created_at,
    )
    if skill.sha256 != version.sha256:
        raise IntegrityProblem(f"{row.author}/{row.name}: stored content does not match its hash")
    return skill


class SkillRepository:
    """All operations of one registry. The caller owns the transaction (session)."""

    def __init__(self, session: Session, registry: m.Registry) -> None:
        self.session = session
        self.registry = registry

    # -- lookups -----------------------------------------------------------------------

    def _row(self, author: str, name: str) -> m.Skill | None:
        return self.session.scalar(
            select(m.Skill).where(
                m.Skill.registry_id == self.registry.id,
                m.Skill.author == author.lower(),
                m.Skill.name == name,
            )
        )

    def _current(self, row: m.Skill) -> m.SkillVersion | None:
        if row.current_version_id is None:
            return None
        return self.session.get(m.SkillVersion, row.current_version_id)

    def get(self, author: str, name: str, sha: str | None = None) -> Skill | None:
        row = self._row(author, name)
        if row is None:
            return None
        if sha is None:
            version = self._current(row)
        else:
            version = self.session.scalar(
                select(m.SkillVersion).where(
                    m.SkillVersion.skill_id == row.id, m.SkillVersion.sha256 == sha
                )
            )
        return None if version is None else _to_skill(row, version)

    def current_sha(self, author: str, name: str) -> str | None:
        row = self._row(author, name)
        version = self._current(row) if row else None
        return version.sha256 if version else None

    def versions(self, author: str, name: str) -> list[dict[str, Any]] | None:
        row = self._row(author, name)
        if row is None:
            return None
        return [
            {
                "sha256": v.sha256,
                "version": v.version,
                "description": v.description,
                "created_at": v.created_at,
                "created_by": v.created_by,
                "current": v.id == row.current_version_id,
            }
            for v in reversed(row.versions)
        ]

    # -- writing -----------------------------------------------------------------------

    def upsert(self, skill: Skill, actor: str) -> tuple[Skill, str]:
        """Store *skill* as a (possibly new) version and make it current.

        Returns the stored skill and what happened: ``created``, ``new-version``, ``rollback``
        (an older, already known version became current again) or ``unchanged``.
        Versions are immutable: an existing hash is never rewritten.
        """
        problems = validate_skill(skill)
        if problems:
            raise InvalidSkill("; ".join(problems))
        row = self._row(skill.author, skill.name)
        outcome = "new-version"
        if row is None:
            row = m.Skill(registry_id=self.registry.id, author=skill.author, name=skill.name)
            self.session.add(row)
            self.session.flush()
            outcome = "created"
        existing = self.session.scalar(
            select(m.SkillVersion).where(
                m.SkillVersion.skill_id == row.id, m.SkillVersion.sha256 == skill.sha256
            )
        )
        if existing is not None:
            outcome = "unchanged" if row.current_version_id == existing.id else "rollback"
            version = existing
        else:
            version = m.SkillVersion(
                skill_id=row.id,
                sha256=skill.sha256,
                version=skill.version,
                description=skill.description,
                content=skill.content,
                extra_json=json.dumps(skill.extra, ensure_ascii=False, sort_keys=True),
                created_by=actor,
            )
            version.labels = [m.VersionLabel(kind="tag", value=t) for t in skill.tags] + [
                m.VersionLabel(kind="topic", value=t) for t in skill.topics
            ]
            version.files = [m.VersionFile(path=p, data=d) for p, d in skill.files.items()]
            self.session.add(version)
            self.session.flush()
        if row.current_version_id != version.id:
            row.current_version_id = version.id
            row.updated_at = m.now()
        self.session.flush()
        return _to_skill(row, version), outcome

    def delete(self, author: str, name: str) -> bool:
        row = self._row(author, name)
        if row is None:
            return False
        row.current_version_id = None
        self.session.flush()
        self.session.execute(delete(m.CollectionSkill).where(m.CollectionSkill.skill_id == row.id))
        self.session.delete(row)
        self.session.flush()
        return True

    # -- search ------------------------------------------------------------------------

    def _base(self):  # type: ignore[no-untyped-def]
        return (
            select(m.Skill, m.SkillVersion)
            .join(m.SkillVersion, m.SkillVersion.id == m.Skill.current_version_id)
            .where(m.Skill.registry_id == self.registry.id)
        )

    def search(self, query: SearchQuery) -> list[SkillSummary]:
        v, s = m.SkillVersion, m.Skill
        conditions = []
        for term in query.terms():
            conditions.append(
                or_(
                    s.name.icontains(term, autoescape=True),
                    v.description.icontains(term, autoescape=True),
                    s.author.icontains(term, autoescape=True),
                    v.content.icontains(term, autoescape=True),
                    exists().where(
                        m.VersionLabel.version_id == v.id,
                        m.VersionLabel.value.icontains(term, autoescape=True),
                    ),
                )
            )
        if query.author:
            conditions.append(s.author == query.author.lower())
        for tag in query.tags:
            conditions.append(
                exists().where(
                    m.VersionLabel.version_id == v.id,
                    m.VersionLabel.kind == "tag",
                    m.VersionLabel.value == tag.lower(),
                )
            )
        for topic in query.topics:
            conditions.append(
                exists().where(
                    m.VersionLabel.version_id == v.id,
                    m.VersionLabel.kind == "topic",
                    m.VersionLabel.value == topic.lower(),
                )
            )
        terms = query.terms()
        relevance = (
            case(
                (s.name.icontains(terms[0], autoescape=True), 0),
                (v.description.icontains(terms[0], autoescape=True), 1),
                else_=2,
            )
            if terms
            else literal(0)
        )
        stmt = (
            self._base()
            .where(*conditions)
            .order_by(relevance, s.author, s.name)
            .limit(query.limit)
            .offset(query.offset)
        )
        return [_summary(row, version) for row, version in self.session.execute(stmt).all()]

    def facets(self, kind: str) -> list[tuple[str, int]]:
        if kind not in FACETS:
            raise ValueError(f"Unknown facet {kind!r}")
        s, v = m.Skill, m.SkillVersion
        if kind == "author":
            stmt = (
                select(s.author, func.count())
                .where(s.registry_id == self.registry.id, s.current_version_id.is_not(None))
                .group_by(s.author)
            )
        else:
            stmt = (
                select(m.VersionLabel.value, func.count())
                .join(v, v.id == m.VersionLabel.version_id)
                .join(s, s.current_version_id == v.id)
                .where(s.registry_id == self.registry.id, m.VersionLabel.kind == kind)
                .group_by(m.VersionLabel.value)
            )
        rows = [(str(value), int(count)) for value, count in self.session.execute(stmt).all()]
        return sorted(rows, key=lambda r: (-r[1], r[0]))

    def count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(m.Skill)
                .where(
                    m.Skill.registry_id == self.registry.id, m.Skill.current_version_id.is_not(None)
                )
            )
            or 0
        )

    def stats(self) -> dict[str, Any]:
        s = m.Skill
        versions = self.session.scalar(
            select(func.count())
            .select_from(m.SkillVersion)
            .join(s, s.id == m.SkillVersion.skill_id)
            .where(s.registry_id == self.registry.id)
        )
        newest = self.session.scalar(
            select(func.max(m.SkillVersion.created_at))
            .join(s, s.id == m.SkillVersion.skill_id)
            .where(s.registry_id == self.registry.id)
        )
        return {
            "registry": self.registry.slug,
            "skills": self.count(),
            "versions": int(versions or 0),
            "last_update": newest,
            "by_author": dict(self.facets("author")),
            "by_tag": dict(self.facets("tag")),
            "by_topic": dict(self.facets("topic")),
        }

    def index(self, limit: int = 500, offset: int = 0) -> dict[str, Any]:
        """A registry-index-like document: every skill with its current hash (for cheap syncing)."""
        stmt = self._base().order_by(m.Skill.author, m.Skill.name).limit(limit).offset(offset)
        rows = self.session.execute(stmt).all()
        return {
            "format": 2,
            "name": self.registry.slug,
            "description": self.registry.description,
            "count": self.count(),
            "skills": [_summary(r, v).to_dict() for r, v in rows],
        }

    # -- collections -------------------------------------------------------------------

    def collections(self) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(
                m.Collection.name, m.Collection.description, func.count(m.CollectionSkill.skill_id)
            )
            .outerjoin(m.CollectionSkill, m.CollectionSkill.collection_id == m.Collection.id)
            .where(m.Collection.registry_id == self.registry.id)
            .group_by(m.Collection.id)
            .order_by(m.Collection.name)
        ).all()
        return [{"name": n, "description": d, "skills": int(c)} for n, d, c in rows]

    def _collection(self, name: str) -> m.Collection | None:
        return self.session.scalar(
            select(m.Collection).where(
                m.Collection.registry_id == self.registry.id, m.Collection.name == name
            )
        )

    def collection_create(self, name: str, description: str = "") -> bool:
        if self._collection(name) is not None:
            return False
        self.session.add(
            m.Collection(registry_id=self.registry.id, name=name, description=description)
        )
        self.session.flush()
        return True

    def collection_members(self, name: str) -> list[str] | None:
        coll = self._collection(name)
        if coll is None:
            return None
        rows = self.session.execute(
            select(m.Skill.author, m.Skill.name)
            .join(m.CollectionSkill, m.CollectionSkill.skill_id == m.Skill.id)
            .where(m.CollectionSkill.collection_id == coll.id)
            .order_by(m.Skill.author, m.Skill.name)
        ).all()
        return [f"{a}/{n}" for a, n in rows]

    def collection_delete(self, name: str) -> bool:
        coll = self._collection(name)
        if coll is None:
            return False
        self.session.execute(
            delete(m.CollectionSkill).where(m.CollectionSkill.collection_id == coll.id)
        )
        self.session.delete(coll)
        self.session.flush()
        return True

    def collection_add(self, name: str, author: str, skill_name: str) -> bool | None:
        coll, row = self._collection(name), self._row(author, skill_name)
        if coll is None or row is None:
            return None
        present = self.session.get(m.CollectionSkill, (coll.id, row.id))
        if present is None:
            self.session.add(m.CollectionSkill(collection_id=coll.id, skill_id=row.id))
            self.session.flush()
        return present is None

    def collection_remove(self, name: str, author: str, skill_name: str) -> bool | None:
        coll, row = self._collection(name), self._row(author, skill_name)
        if coll is None or row is None:
            return None
        present = self.session.get(m.CollectionSkill, (coll.id, row.id))
        if present is not None:
            self.session.delete(present)
            self.session.flush()
        return present is not None


def _summary(row: m.Skill, version: m.SkillVersion) -> SkillSummary:
    return SkillSummary(
        author=row.author,
        name=row.name,
        version=version.version,
        description=version.description,
        tags=sorted(label.value for label in version.labels if label.kind == "tag"),
        topics=sorted(label.value for label in version.labels if label.kind == "topic"),
        sha256=version.sha256,
        updated_at=version.created_at,
    )
