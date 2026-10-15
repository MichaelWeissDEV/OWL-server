<p align="center"><img src="_static/owl.png" alt="OWL logo" width="160"></p>

# OWL Server

**A self-hostable, PostgreSQL-backed skill registry with a web dashboard for [OWL](https://github.com/MichaelWeissDEV/OWL).**

```{admonition} Development status: Alpha
:class: warning

OWL Server is under active development. The HTTP API, the database schema and the configuration can
still change. Be careful with production use and back up your database. Bug reports and
contributions are welcome – see {doc}`development/contributing`. The server is optional: the OWL CLI
works fully without it. The CLI itself is documented at
[owl-skills.readthedocs.io](https://owl-skills.readthedocs.io).
```

OWL Server stores skills **completely in PostgreSQL** – every skill with all of its versions and files –
and speaks the HTTP API of the OWL command line, so `owl search`, `owl install`, `owl pull` and
`owl push` work against it unchanged. It is **open by default** (no restriction) and becomes an
access-controlled team server when you want it to.

```{mermaid}
flowchart LR
    CLI[owl CLI<br/>search · pull · push · install] -- HTTPS --> RP[reverse proxy / TLS]
    DASH[web dashboard] -- HTTPS --> RP
    RP --> API[OWL Server API<br/>FastAPI]
    API --> PG[(PostgreSQL)]
    API -. OIDC / OAuth2 / LDAP .-> IDP[Identity provider<br/>Keycloak, AD, GitHub ...]
```

::::{grid} 1 2 2 3
:gutter: 3

:::{grid-item-card} Getting started
:link: getting-started/index
:link-type: doc
Run the server with Docker, open the dashboard and push your first skill.
:::

:::{grid-item-card} Guide
:link: guide/index
:link-type: doc
Dashboard, users and roles, identity providers (Keycloak, LDAP/AD, GitHub, Kerberos via proxy).
:::

:::{grid-item-card} Reference
:link: reference/index
:link-type: doc
All configuration variables, the insecure switches and the HTTP API.
:::

:::{grid-item-card} Operations
:link: operations/index
:link-type: doc
Deployment, TLS reverse proxy, backups, hardening and troubleshooting.
:::

:::{grid-item-card} Development
:link: development/index
:link-type: doc
Architecture, tests, contributing and licensing.
:::

:::{grid-item-card} FAQ
:link: faq
:link-type: doc
Short answers to the usual questions.
:::
::::

## Feature overview

- **Immutable versions** – every change becomes a new hash-addressed version; rollbacks are explicit.
- **Registries** – several per server, each public or private, with reader / publisher / admin roles.
- **Open by default** – no restriction until you press *Secure this server* in the dashboard.
- **Dashboard** – browse, diff and import skills; manage registries, users, tokens, settings and the audit log.
- **Users and identity** – simple built-in accounts (Argon2id), API tokens with scopes, OpenID Connect
  (Keycloak and others), OAuth 2.0 (GitHub), LDAP / Active Directory, Kerberos / SAML via an
  authenticating reverse proxy.
- **Secure by default, insecure only on purpose** – anything that weakens security needs a long
  `ALLOW_INSECURE_…` switch and is logged as a warning ({ref}`insecure-switches`).
- **Operations** – Docker Compose, health and readiness endpoints, Alembic migrations, audit log.

```{toctree}
:maxdepth: 2
:caption: Documentation
:hidden:

getting-started/index
guide/index
reference/index
operations/index
development/index
faq
changelog
```
