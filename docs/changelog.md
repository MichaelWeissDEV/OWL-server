# Changelog

OWL Server is alpha; versions are not released yet.

## Unreleased

- Web dashboard (React, TypeScript, Mantine) with browse/diff/import, registries, users, tokens, audit log and settings.
- Open by default; *Secure this server* in the dashboard; `OWL_SERVER_OPEN` override.
- Identity providers: OpenID Connect, OAuth 2.0 (GitHub preset), LDAP / Active Directory, authenticating proxy (Kerberos, SAML).
- Insecure behaviour only through long `OWL_SERVER_ALLOW_INSECURE_…` switches, reported at start-up.
- PostgreSQL storage with Alembic migrations, registries, roles, personal and service tokens, audit log.
- Docker Compose deployment with an optional dashboard profile.
