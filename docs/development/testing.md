# Testing

| Suite | Command | Notes |
| --- | --- | --- |
| Server | `uv run pytest` | SQLite by default |
| Server on PostgreSQL | `OWL_SERVER_TEST_POSTGRES_URL=postgresql://postgres:pw@localhost:55433/owl_server_test uv run pytest` | run before releases |
| Dashboard unit tests | `cd dashboard && npm test` | vitest + Testing Library |
| Dashboard end to end | `cd dashboard && npm run e2e` | Playwright (Chromium); set `E2E_BASE_URL` to test a running stack |
| Static checks | `ruff`, `mypy`, `eslint`, `tsc` | also run in CI |

Identity providers (OIDC, OAuth, LDAP) are tested against mocks. They have **not** been verified
against a real Keycloak, Active Directory or GitHub installation yet – please report problems.
