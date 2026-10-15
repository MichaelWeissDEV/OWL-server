# Deployment with Docker Compose

The repository ships a `compose.yaml` with two services: **PostgreSQL** and the **OWL API**. (A web
dashboard is a separate, optional service that gets its own compose profile and is not required.)

```text
PostgreSQL  <-  OWL API   (127.0.0.1:8765)  <-  reverse proxy (TLS)  <-  clients
```

## Start

```console
$ git clone https://github.com/MichaelWeissDEV/owl-server.git && cd owl-server
$ cp .env.example .env
$ $EDITOR .env                    # POSTGRES_PASSWORD (required); OWL_SERVER_ADMIN_TOKEN is optional
$ docker compose up -d --build
$ curl http://127.0.0.1:8765/api/v1/ready
{"status":"ready","revision":"0002","version":"0.1.0"}
```

`docker compose` refuses to start if `POSTGRES_PASSWORD` is missing – there are **no hard-coded passwords**.
`OWL_SERVER_ADMIN_TOKEN` is optional: without it the server starts **open** (no login, bound to
`127.0.0.1`) and you secure it in the dashboard ({doc}`/guide/identity`). Add the optional dashboard with
`docker compose --profile dashboard up -d --build` ({doc}`/guide/dashboard`).

## What the stack does

- The API starts only after PostgreSQL reports **healthy** (`pg_isready` health check) and applies the
  Alembic **migrations** at startup (`OWL_SERVER_AUTO_MIGRATE`, default on). `GET /api/v1/ready` is 200
  only when the database answers and the schema is at the newest revision; `GET /api/v1/health` is a pure
  liveness check.
- Data lives in the named volume `pgdata` and survives `docker compose down` (not `down -v`).
- The database is on an **internal network** and is not published to the host; only the API is, on
  `127.0.0.1`.
- Graceful shutdown: containers get a stop grace period; uvicorn finishes in-flight requests on SIGTERM.

## Container hardening

| Measure | How |
| --- | --- |
| unprivileged user | uid 10001, no login shell |
| read-only root filesystem | `read_only: true`, `tmpfs: /tmp` |
| no extra privileges | `cap_drop: [ALL]`, `no-new-privileges` |
| small image | multi-stage build on `python:3.13-slim`, no compiler or git in the final image |
| resource limits | `deploy.resources.limits.memory: 512m` (adjust to your workload) |
| secrets not in logs | configuration values are never logged; `*_FILE` variants read secrets from files |

### Secrets from files

Every setting can be given as `OWL_SERVER_<NAME>_FILE` pointing to a file (Docker/Kubernetes
secrets). Example for Compose secrets:

```yaml
services:
  api:
    environment:
      OWL_SERVER_ADMIN_TOKEN_FILE: /run/secrets/owl_admin_token
    secrets: [owl_admin_token]
secrets:
  owl_admin_token:
    file: ./secrets/owl_admin_token.txt
```

## First steps after the start

```console
$ docker compose exec api owl-server create-admin alice          # prompts for a password (needs OWL_SERVER_LOCAL_ACCOUNTS=true to log in)
$ curl -X POST http://127.0.0.1:8765/api/v1/registries \
    -H "Authorization: Bearer $OWL_SERVER_ADMIN_TOKEN" -H 'content-type: application/json' \
    -d '{"slug": "team", "visibility": "private"}'
$ docker compose exec api owl-server create-token team --role publisher --name ci --ttl-hours 720
owl_…                                     # shown once - store it as a CI secret
```

The bootstrap admin token is meant for setup; afterwards prefer named accounts or OIDC and keep the token
in a secret store (or remove it from the environment).

## TLS and reverse proxy

The API speaks plain HTTP. Terminate TLS in a reverse proxy (see {doc}`reverse-proxy`);
the image runs uvicorn with `--proxy-headers` so client addresses in the audit log are the real ones. Only
list proxies you trust in `--forwarded-allow-ips` when the container is reachable by others. Allow request
bodies of about `OWL_SERVER_MAX_BODY_MB` plus overhead.

## Backup and restore

All state is in PostgreSQL:

```console
$ docker compose exec -T db pg_dump -U owl -Fc owl > owl-$(date +%F).dump
$ docker compose exec -T db pg_restore -U owl -d owl --clean < owl-2026-10-15.dump
```

The registry content can additionally be exported as plain files (`GET /r/<slug>/api/v1/export`).

## Upgrades

```console
$ git pull && docker compose up -d --build
```

Migrations are applied on start. Back up first. The image installs the OWL core from the address in the
build argument `OWL_SPEC` (default: the `master` branch of the OWL repository); pin it to a tag for
reproducible builds.

## Checklist

- [ ] strong `POSTGRES_PASSWORD`, not committed; the server **secured** (Settings → Secure this server) before it is reachable by others
- [ ] TLS reverse proxy in front, port bound to `127.0.0.1`
- [ ] backups of PostgreSQL tested
- [ ] mode chosen deliberately ({doc}`/guide/access-and-roles`)
- [ ] resource limits adjusted; logs collected
