# Server API

Base path `/api/v1` (the default registry) and `/r/{registry}/api/v1` (any registry). OpenAPI at
`/docs` and `/openapi.json`. The skill endpoints are the ones the OWL CLI uses
([OWL CLI documentation](https://owl-skills.readthedocs.io/en/latest/reference/http-api.html)); the server adds versions, ETags and administration.

Errors are `{"detail": "..."}` with these codes: `401` authentication required/invalid token, `403` not
allowed for your role, `404` not found (also for private registries without access), `409` conflict,
`413` body too large, `422` validation, `429` rate limited.

## System

| Endpoint | Role | |
| --- | --- | --- |
| `GET /health` | open | liveness |
| `GET /ready` | open | database reachable and schema at head (503 otherwise) |
| `GET /registries` | any | registries visible to the caller |
| `POST /registries` | server admin | `{slug, name, description, visibility}` |
| `PATCH /registries/{slug}` | registry admin (visibility: server admin) | |
| `DELETE /registries/{slug}[?force=true]` | server admin | |
| `GET\|PUT\|DELETE /registries/{slug}/members[/{user}]` | registry admin | `{"role": "reader\|publisher\|admin"}` |

## Skills (per registry)

| Endpoint | Role | |
| --- | --- | --- |
| `GET /info` | reader | name, server version, skills, `writable`, `private`, `mode`, your `role` |
| `GET /skills?q=&author=&tag=&topic=&limit=&offset=` | reader | search (same semantics as the CLI) |
| `GET\|HEAD /skills/{author}/{name}[?version=<sha256>]` | reader | the skill; `ETag` = content hash; `If-None-Match` → 304 |
| `PUT /skills/{author}/{name}` | publisher | create / new version / rollback (201 when created) |
| `DELETE /skills/{author}/{name}` | publisher | removes the skill and **all** its versions |
| `GET /skills/{author}/{name}/versions` | reader | newest first, with `current` |
| `GET /skills/{author}/{name}/versions/{sha}` | reader | one immutable version |
| `GET /skills/{author}/{name}/download[?version=]` | reader | zip (`<name>/SKILL.md`, `skill.json`, files) |
| `GET /facets/{author\|tag\|topic}`, `GET /tags` | reader | values with counts |
| `GET /stats` | reader | counts per author/tag/topic, versions, last update |
| `GET /index[?limit=&offset=]` | reader | listing with content hashes, for cheap syncing |
| `GET /export` | reader | the registry as a zip in git-registry layout |
| `GET /collections`, `GET /collections/{name}` | reader | |
| `POST /collections`, `DELETE /collections/{name}` | publisher | |
| `PUT\|DELETE /collections/{name}/skills/{author}/{skill}` | publisher | |

### Efficient updates

Use `HEAD` or a conditional `GET` to avoid downloading unchanged skills:

```console
$ curl -sI -H "Authorization: Bearer $T" https://skills.example.com/r/team/api/v1/skills/me/pdf | grep -i etag
etag: "9f2c…"
$ curl -s -H "Authorization: Bearer $T" -H 'If-None-Match: "9f2c…"' …/skills/me/pdf -w '%{http_code}\n'
304
```

Old versions are immutable, so `GET …/versions/{sha}` responses of public registries are cacheable.

## Authentication

| Endpoint | |
| --- | --- |
| `GET /auth/config` | which login methods exist (for a login page) |
| `POST /auth/login` | `{username, password}` → session token (local accounts) |
| `POST /auth/logout`, `GET /auth/me`, `POST /auth/password` | |
| `GET\|POST /auth/tokens`, `DELETE /auth/tokens/{id}` | personal tokens |
| `GET /auth/oidc/login[?json=1]`, `GET /auth/oidc/callback`, `POST /auth/oidc/exchange` | {doc}`/guide/oidc` |

## Administration (server admin)

`GET|POST /admin/users`, `PATCH /admin/users/{username}` (`active`, `is_admin`, `password`),
`GET|POST /admin/tokens`, `DELETE /admin/tokens/{id}`, `GET /admin/audit[?limit=&action=]`.
