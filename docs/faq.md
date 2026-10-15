# FAQ

**Do I need the server to use OWL?** No. The OWL CLI works standalone with SQLite or git. The server is for
sharing skills inside a team.

**Why is the server open by default?** So that setting it up needs no accounts at all. It logs a
warning while open. Press *Secure this server* in the dashboard (or set an admin token or an identity
provider) as soon as others can reach it.

**Can I use Keycloak, Active Directory or GitHub for login?** Yes: OpenID Connect, LDAP/Active Directory
and OAuth 2.0 are built in ({doc}`guide/identity`). Kerberos/SPNEGO and SAML work through an
authenticating reverse proxy.

**Can I allow LDAP without TLS?** Only with `OWL_SERVER_ALLOW_INSECURE_LDAP_WITHOUT_TLS=true`
({ref}`insecure-switches`). It is logged as a warning at every start.

**Is the dashboard required?** No. Everything is available through the API and the CLI.

**Does it work with SQLite?** For tests and tiny setups, yes; PostgreSQL is the supported production database.

**How do I upgrade?** Back up, pull, rebuild: `docker compose up -d --build`. Migrations run on start.
