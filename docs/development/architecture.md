# Architecture

```{mermaid}
flowchart TB
    R[routes<br/>auth · system · admin · skills] --> D[deps<br/>principal + permissions]
    D --> A[access<br/>open / secured]
    D --> E[external<br/>OIDC · OAuth · LDAP · proxy]
    R --> Q[repository<br/>skills, versions, registries]
    Q --> M[(SQLAlchemy models<br/>PostgreSQL / SQLite)]
    M --- AL[Alembic migrations]
```

| Module | Purpose |
| --- | --- |
| `config.py` | environment → validated `Settings`, including the insecure switches |
| `access.py` | open vs. secured state (environment, providers, database flag) |
| `permissions.py`, `deps.py` | who is calling and what they may do, per registry |
| `external.py`, `oidc.py`, `oauth.py`, `ldap_auth.py` | identity providers and the common role mapping |
| `repository.py`, `models.py` | storage of registries, skills, versions, files |
| `routes/` | HTTP endpoints (the CLI-compatible API and the administration API) |
| `migrations/` | Alembic revisions, packaged with the application |
| `dashboard/` | React + TypeScript single-page application, served by nginx |

The data model, hashing and validation come from the OWL core package, so server and CLI never
disagree about what a skill is.
