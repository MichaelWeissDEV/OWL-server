<p align="center">
  <img src="assets/owl-256.png" alt="OWL logo - a friendly owl on a branch" width="160">
</p>

<h1 align="center">OWL Server</h1>

<p align="center"><b>A self-hostable, PostgreSQL-backed skill registry for <a href="https://github.com/MichaelWeissDEV/OWL">OWL</a>.</b></p>

<p align="center">
  <img alt="Development status: Alpha" src="https://img.shields.io/badge/status-alpha-orange">
  <img alt="Version 0.1.0" src="https://img.shields.io/badge/version-0.1.0-blue">
  <img alt="Python 3.13+" src="https://img.shields.io/badge/python-3.13%2B-3776AB?logo=python&amp;logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/database-PostgreSQL-336791?logo=postgresql&amp;logoColor=white">
  <a href="https://github.com/MichaelWeissDEV/owl-server/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/MichaelWeissDEV/owl-server/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://owl-skills.readthedocs.io"><img alt="Documentation" src="https://img.shields.io/badge/docs-Read%20the%20Docs-8CA1AF?logo=readthedocs&amp;logoColor=white"></a>
  <a href="https://github.com/MichaelWeissDEV/OWL"><img alt="OWL CLI" src="https://img.shields.io/badge/client-OWL%20CLI-8b5a2b"></a>
</p>

> **Development Status: Alpha.** OWL Server is under active development. The HTTP API, the database
> schema and the configuration can still change. Be careful with production use and back up your
> database. Bug reports and contributions are welcome.

OWL Server stores skills **completely in PostgreSQL** - every skill with all of its versions and
files - and speaks the HTTP API of the [OWL](https://github.com/MichaelWeissDEV/OWL) command line, so
`owl search`, `owl install`, `owl pull`, `owl push` just work against it. Git registries stay the
primary way to publish skills publicly; the server is for teams that want one central, access
controlled place.

- **Versions** - every change becomes a new immutable, hash-addressed version; rollbacks are explicit.
- **Registries** - several registries per server, each public or private, with reader / publisher /
  admin roles.
- **Three modes** - `public`, `private` or `mixed`.
- **Open by default** - a fresh server has no restrictions; manage everything in the dashboard and
  press *Secure this server* (or set an admin token / identity provider) when you want access control.
- **Dashboard** - web UI to browse, diff and import skills and to manage registries, users, tokens,
  settings and the audit log (`dashboard/`, React + TypeScript, served by nginx with a strict CSP).
- **Users and identity** - simple built-in accounts (Argon2id), API tokens with scopes, and pluggable
  providers: OpenID Connect (Keycloak, Entra, ...), OAuth2 (GitHub), LDAP / Active Directory, and
  Kerberos / SAML through an authenticating reverse proxy. Providers map groups to roles.
- **Efficient** - ETag / `If-None-Match`, paging, trigram indexes on PostgreSQL.
- **Operations** - Docker Compose, health and readiness endpoints, Alembic migrations, audit log.
- **Shared core** - the data model, hashing and validation come from the OWL package, so server and
  CLI never disagree about what a skill is.

## Quickstart (Docker)

```bash
git clone https://github.com/MichaelWeissDEV/owl-server.git && cd owl-server
cp .env.example .env       # set POSTGRES_PASSWORD (see the comments)
docker compose --profile dashboard up -d --build   # dashboard on http://127.0.0.1:8080
curl http://127.0.0.1:8765/api/v1/ready
```

Then, from any machine with the OWL CLI:

```bash
# open server: no token needed; once secured use a token created in the dashboard
export OWL_TOKEN=...
owl remote add company http://127.0.0.1:8765 --token-env OWL_TOKEN
owl push --all -r company
owl search security -r company
owl install secure-review -r company
```

The server is open until you secure it - do not expose an open server beyond localhost. Put a TLS reverse proxy in front before exposing the server beyond localhost. The database is on an
internal network and is never published.

## Documentation

Deployment, authentication, roles, OpenID Connect, the HTTP API and operations are documented in the
[OWL documentation](https://owl-skills.readthedocs.io) (section *Server*).

## Development

```bash
# the shared OWL core is used from the sibling checkout:  workspace/OWL  and  workspace/owl-server
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
OWL_SERVER_TEST_POSTGRES_URL=postgresql://postgres:pw@localhost:55433/owl_server_test uv run pytest
```

Dashboard: `cd dashboard && npm ci && npm run dev` (tests: `npm test`, `npm run e2e`).

Layout: `src/owl_server/` (config, models, repository, accounts, external/oidc/oauth/ldap, routes, app, cli), `dashboard/`,
`src/owl_server/migrations/` (Alembic), `tests/`, `Dockerfile`, `compose.yaml`.

## License

No license has been chosen yet (all rights reserved by the author) - see the note in the
[OWL repository](https://github.com/MichaelWeissDEV/OWL#license).
