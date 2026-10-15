"""The per-registry skill API. Mounted twice: ``/api/v1`` (default registry, the paths OWL's
``RemoteStore`` uses) and ``/r/{registry}/api/v1`` (any registry - use that URL as the remote)."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from owl.models import InvalidSkill, OwlError, SearchQuery, Skill
from starlette.background import BackgroundTask

from owl_server import __version__, audit
from owl_server.deps import RegistryDep, client_ip, effective_visibility
from owl_server.repository import FACETS

router = APIRouter()


def _etag(sha: str) -> str:
    return f'"{sha}"'


@router.get("/info")
def info(ctx: RegistryDep) -> dict[str, Any]:
    return {
        "name": "owl",
        "server": "owl-server",
        "version": __version__,
        "registry": ctx.registry.slug,
        "skills": ctx.repo.count(),
        "writable": ctx.role in ("publisher", "admin"),
        "private": effective_visibility(ctx.settings, ctx.registry) == "private",
        "mode": ctx.settings.mode,
        "role": ctx.role,
    }


@router.get("/skills")
def search(
    ctx: RegistryDep,
    q: str = "",
    author: str | None = None,
    tag: Annotated[list[str] | None, Query()] = None,
    topic: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    query = SearchQuery(
        text=q, author=author, tags=tag or [], topics=topic or [], limit=limit, offset=offset
    )
    return [s.to_dict() for s in ctx.repo.search(query)]


@router.api_route("/skills/{author}/{name}", methods=["GET", "HEAD"])
def get_skill(
    request: Request, ctx: RegistryDep, author: str, name: str, version: str | None = None
) -> Response:
    """The full skill; ``ETag`` is the content hash, so clients can revalidate with
    ``If-None-Match`` and only download what changed. ``?version=<sha256>`` selects an older version."""
    skill = ctx.repo.get(author, name, sha=version)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    etag = _etag(skill.sha256)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers)
    return JSONResponse(skill.to_dict(), headers=headers)


@router.put("/skills/{author}/{name}")
def put_skill(
    request: Request,
    ctx: RegistryDep,
    author: str,
    name: str,
    body: Annotated[dict[str, Any], Body()],
) -> Response:
    """Create or update a skill. A changed skill becomes a *new immutable version*."""
    ctx.require("publisher")
    try:
        skill = Skill.from_dict(body)
    except (KeyError, ValueError, TypeError, OwlError) as exc:
        raise HTTPException(422, f"Malformed skill: {exc}") from exc
    if (skill.author, skill.name) != (author.lower(), name):
        raise HTTPException(422, "Skill author/name does not match the URL")
    try:
        stored, outcome = ctx.repo.upsert(skill, ctx.principal.actor)
    except InvalidSkill as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(
        ctx.session,
        ctx.principal,
        f"skill.{outcome}",
        f"{ctx.registry.slug}:{stored.ref}",
        f"sha256={stored.sha256} version={stored.version}",
        client_ip(request),
    )
    ctx.session.commit()
    return JSONResponse(
        stored.to_dict(),
        status_code=201 if outcome == "created" else 200,
        headers={"ETag": _etag(stored.sha256)},
    )


@router.delete("/skills/{author}/{name}")
def delete_skill(request: Request, ctx: RegistryDep, author: str, name: str) -> dict[str, bool]:
    ctx.require("publisher")
    if not ctx.repo.delete(author, name):
        raise HTTPException(404, "Skill not found")
    audit.record(
        ctx.session,
        ctx.principal,
        "skill.delete",
        f"{ctx.registry.slug}:{author}/{name}",
        ip=client_ip(request),
    )
    ctx.session.commit()
    return {"deleted": True}


@router.get("/skills/{author}/{name}/versions")
def list_versions(ctx: RegistryDep, author: str, name: str) -> list[dict[str, Any]]:
    versions = ctx.repo.versions(author, name)
    if versions is None:
        raise HTTPException(404, "Skill not found")
    return versions


@router.get("/skills/{author}/{name}/versions/{sha}")
def get_version(ctx: RegistryDep, author: str, name: str, sha: str) -> JSONResponse:
    skill = ctx.repo.get(author, name, sha=sha)
    if skill is None:
        raise HTTPException(404, "Version not found")
    return JSONResponse(
        skill.to_dict(),
        headers={
            "ETag": _etag(skill.sha256),
            "Cache-Control": "public, max-age=31536000, immutable"
            if ctx.registry.visibility == "public"
            else "private",
        },
    )


def skill_zip(skill: Skill) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{skill.name}/SKILL.md", skill.content)
        zf.writestr(
            f"{skill.name}/skill.json",
            json.dumps(skill.meta(), indent=2, ensure_ascii=False) + "\n",
        )
        for path, data in sorted(skill.files.items()):
            zf.writestr(f"{skill.name}/{path}", data)
    return buffer.getvalue()


@router.get("/skills/{author}/{name}/download")
def download(ctx: RegistryDep, author: str, name: str, version: str | None = None) -> Response:
    """The complete skill as a zip archive (``<name>/SKILL.md``, ``skill.json``, bundled files)."""
    skill = ctx.repo.get(author, name, sha=version)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    return Response(
        skill_zip(skill),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{skill.name}.zip"',
            "ETag": _etag(skill.sha256),
        },
    )


@router.get("/facets/{kind}")
def facets(ctx: RegistryDep, kind: str) -> list[dict[str, Any]]:
    if kind not in FACETS:
        raise HTTPException(404, f"Unknown facet '{kind}'")
    return [{"value": v, "count": n} for v, n in ctx.repo.facets(kind)]


@router.get("/tags")
def tags(ctx: RegistryDep) -> list[dict[str, Any]]:
    return [{"value": v, "count": n} for v, n in ctx.repo.facets("tag")]


@router.get("/stats")
def stats(ctx: RegistryDep) -> dict[str, Any]:
    return ctx.repo.stats()


@router.get("/index")
def index(
    ctx: RegistryDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """A registry-index-style listing (with content hashes) for cheap synchronisation."""
    return ctx.repo.index(limit, offset)


@router.get("/export")
def export_registry(ctx: RegistryDep) -> FileResponse:
    """The registry as a zip in OWL's git-registry layout (``skills/<name>/``, ``index.json``, ...),
    ready to become a git repository (server -> git registry)."""
    from owl import registry as owl_registry
    from owl.stores.directory import DirectoryStore

    tmp = Path(tempfile.mkdtemp(prefix="owl-export-"))
    root = tmp / ctx.registry.slug
    root.mkdir(parents=True)
    owl_registry.scaffold(  # plain files, no git binary needed
        root,
        name=ctx.registry.slug,
        description=ctx.registry.description or f"Registry {ctx.registry.slug}",
    )
    store = DirectoryStore(root)
    skipped: list[str] = []
    for summary in ctx.repo.search(SearchQuery(limit=100000)):
        skill = ctx.repo.get(summary.author, summary.name)
        if skill is None:
            continue
        try:
            store.upsert(skill)
        except OwlError as exc:  # e.g. two authors share a name: flat layout cannot hold both
            skipped.append(f"{summary.ref}: {exc}")
    owl_registry.write_index(root)
    if skipped:
        (root / "EXPORT-SKIPPED.txt").write_text("\n".join(skipped) + "\n", "utf-8")
    archive = tmp / f"{ctx.registry.slug}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(root.rglob("*")):
            if file.is_file() and ".git" not in file.relative_to(root).parts:
                zf.write(file, file.relative_to(root).as_posix())
    import shutil

    return FileResponse(
        archive,
        media_type="application/zip",
        filename=f"{ctx.registry.slug}.zip",
        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
    )


# -- collections ---------------------------------------------------------------------------


@router.get("/collections")
def collections(ctx: RegistryDep) -> list[dict[str, Any]]:
    return ctx.repo.collections()


@router.get("/collections/{name}")
def collection(ctx: RegistryDep, name: str) -> dict[str, Any]:
    members = ctx.repo.collection_members(name)
    if members is None:
        raise HTTPException(404, "Collection not found")
    return {"name": name, "skills": members}


@router.post("/collections", status_code=201)
def create_collection(ctx: RegistryDep, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    ctx.require("publisher")
    name = str(body.get("name", "")).strip()
    if not name or "/" in name or len(name) > 100:
        raise HTTPException(422, "Collection names must be 1-100 characters without '/'")
    if not ctx.repo.collection_create(name, str(body.get("description", ""))):
        raise HTTPException(409, "Collection already exists")
    audit.record(ctx.session, ctx.principal, "collection.create", f"{ctx.registry.slug}:{name}")
    ctx.session.commit()
    return {"name": name}


@router.delete("/collections/{name}")
def delete_collection(ctx: RegistryDep, name: str) -> dict[str, bool]:
    ctx.require("publisher")
    if not ctx.repo.collection_delete(name):
        raise HTTPException(404, "Collection not found")
    audit.record(ctx.session, ctx.principal, "collection.delete", f"{ctx.registry.slug}:{name}")
    ctx.session.commit()
    return {"deleted": True}


@router.put("/collections/{name}/skills/{author}/{skill}")
def collection_add(ctx: RegistryDep, name: str, author: str, skill: str) -> dict[str, bool]:
    ctx.require("publisher")
    added = ctx.repo.collection_add(name, author, skill)
    if added is None:
        raise HTTPException(404, "Collection or skill not found")
    ctx.session.commit()
    return {"added": added}


@router.delete("/collections/{name}/skills/{author}/{skill}")
def collection_remove(ctx: RegistryDep, name: str, author: str, skill: str) -> dict[str, bool]:
    ctx.require("publisher")
    removed = ctx.repo.collection_remove(name, author, skill)
    if removed is None:
        raise HTTPException(404, "Collection or skill not found")
    ctx.session.commit()
    return {"removed": removed}
