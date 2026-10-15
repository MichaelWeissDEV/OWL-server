# Identity and access

OWL Server starts **open** and grows with you: from "no login at all" through built-in user
management to a company identity provider. Each step is optional.

```{mermaid}
flowchart LR
    A[Open<br/>no login] -->|"dashboard: Secure this server"| B[Secured<br/>local accounts]
    B --> C[+ identity provider<br/>OIDC · OAuth2 · LDAP/AD · proxy]
    C -. optional .-> B
```

## 1. Open mode (the default)

A fresh server has **no restriction**: nobody has to log in and everybody is an administrator. That is
the easiest way to try it on a laptop or run it inside a trusted network, and the Compose file only
publishes the port on `127.0.0.1`.

- The dashboard shows a permanent yellow banner, the log prints a warning, `GET /api/v1/setup/status`
  reports `"open": true`.
- `owl-server serve --host 0.0.0.0` in open mode prints an explicit warning: *anyone who can reach the
  port is an administrator*.
- The OWL CLI needs no token: `owl remote add lab http://host:8765`.

The server is open until **one of these** happens:

| Event | Result |
| --- | --- |
| an administrator uses **Settings → Secure this server** (or `POST /api/v1/setup/secure`) | creates the first admin account and requires authentication from now on |
| `OWL_SERVER_ADMIN_TOKEN`, or any identity provider, is configured | secured from the start |
| `OWL_SERVER_OPEN=false` | secured; `OWL_SERVER_OPEN=true` forces open mode regardless of everything else |

Securing needs a way to log in afterwards, so it is refused while no administrator, admin token or
identity provider exists. Re-opening (Settings → *Switch back to open mode*) needs a typed
confirmation. A stale or invalid token never locks anybody out of an *open* server.

## 2. Built-in user management

Users are created and managed **in the dashboard** (*Users*): create, disable, make administrator,
reset the password, assign registry roles, delete. No extra service is needed.

- Passwords: **Argon2id**, at least 12 characters, never stored or logged in clear text.
- A user's access comes from **registry memberships** (reader / publisher / admin) plus the optional
  *server administrator* flag ({doc}`/guide/access-and-roles`).
- Every user can create personal API tokens (for the OWL CLI) and change their password in *Profile*.
- Service tokens for CI are created under *Service tokens*.
- Command line alternative: `owl-server create-admin NAME`.

This is the right size for a small team. When you want more - single sign-on, central password
policy, groups - connect an identity provider; the same screens keep working.

## 3. Identity providers

Several can be active at the same time; users pick on the login page. Account provisioning is the
same for all of them:

- the account is created **on first sign-in** (`…_AUTO_CREATE=false` restricts sign-in to accounts an
  administrator created beforehand);
- external accounts have **no rights by default** - rights come from the group mapping or are granted
  in the dashboard;
- group mappings are re-applied at **every** sign-in: the mapped registries follow the directory
  (a removed group removes the membership); `…_ADMIN_VALUES` controls the administrator flag only when
  set, so manual grants are not reset;
- a username that exists as a **local** account is never taken over - the external user gets the suffix
  `@<provider>`;
- disabling a user in the dashboard blocks them immediately, whatever the provider says.

All three mapping variables exist per provider (`OIDC_`, `OAUTH_`, `LDAP_`, `PROXY_`):

| Variable | Meaning |
| --- | --- |
| `…_ADMIN_VALUES` | comma separated group/role values that make a user a server admin |
| `…_REGISTRY_ROLES` | JSON `{"group": {"registry-slug": "reader\|publisher\|admin"}}` |
| `…_AUTO_CREATE` | create accounts on first sign-in (default true) |

### OpenID Connect

Keycloak, Authentik, Microsoft Entra ID, Okta, Google, Auth0 and every other OIDC provider. See
{doc}`/guide/oidc` (authorization code flow with PKCE, JWKS validation, `https` required).

### OAuth 2.0 (GitHub and others)

For providers *without* OpenID Connect. OWL runs the authorization code flow with PKCE, then asks the
provider's **user-info endpoint** who the user is.

```ini
# GitHub in three lines (preset fills in the endpoints)
OWL_SERVER_OAUTH_PRESET=github
OWL_SERVER_OAUTH_CLIENT_ID=Iv1.abc123
OWL_SERVER_OAUTH_CLIENT_SECRET_FILE=/run/secrets/github_secret
OWL_SERVER_OAUTH_REDIRECT_URI=https://skills.example.com/auth/callback
OWL_SERVER_OAUTH_ALLOWED_USERS=alice,bob          # important - see below
```

```{warning}
"Sign in with GitHub" authenticates **anybody with a GitHub account**. Restrict it with
`OWL_SERVER_OAUTH_ALLOWED_USERS` or turn `OWL_SERVER_OAUTH_AUTO_CREATE` off and pre-create accounts.
New accounts have no registry access by default, but they can read public registries.
```

Generic provider: set `OAUTH_AUTHORIZE_URL`, `OAUTH_TOKEN_URL`, `OAUTH_USERINFO_URL`, `OAUTH_SCOPES`,
and the JSON field names `OAUTH_ID_FIELD` / `OAUTH_USERNAME_FIELD` / `OAUTH_EMAIL_FIELD` /
`OAUTH_GROUPS_FIELD`. All endpoints must be `https://`.

### LDAP and Active Directory

Password login, checked by the directory. OWL searches the user with a **service account**, then
**binds as the user** with the password they typed - OWL never sees a hash and never stores the
password.

```ini
# Active Directory
OWL_SERVER_LDAP_URL=ldaps://dc.corp.example.com
OWL_SERVER_LDAP_BIND_DN=CN=owl-svc,OU=Service Accounts,DC=corp,DC=example,DC=com
OWL_SERVER_LDAP_BIND_PASSWORD_FILE=/run/secrets/ldap_bind
OWL_SERVER_LDAP_USER_BASE=OU=People,DC=corp,DC=example,DC=com
OWL_SERVER_LDAP_USER_FILTER=(sAMAccountName={username})        # AD default
OWL_SERVER_LDAP_ADMIN_VALUES=OWL Admins
OWL_SERVER_LDAP_REGISTRY_ROLES={"OWL Publishers": {"team": "publisher"}}

# OpenLDAP / FreeIPA instead:
#   OWL_SERVER_LDAP_USER_FILTER=(uid={username})
#   OWL_SERVER_LDAP_USERNAME_ATTR=uid   OWL_SERVER_LDAP_GROUP_ATTR=memberOf
```

| Variable | Default | |
| --- | --- | --- |
| `LDAP_URL` | required | `ldaps://…` (or `ldap://…` with `LDAP_START_TLS=true`) |
| `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD` | required | read-only service account |
| `LDAP_USER_BASE` | required | where users live |
| `LDAP_USER_FILTER` | `(sAMAccountName={username})` | must contain `{username}` |
| `LDAP_USERNAME_ATTR`, `LDAP_EMAIL_ATTR`, `LDAP_GROUP_ATTR` | `sAMAccountName`, `mail`, `memberOf` | |
| `LDAP_START_TLS`, `LDAP_CA_FILE`, `LDAP_TIMEOUT` | false, -, 8 | TLS validation is always on (see [](#insecure-switches)) |

Groups can be named by full DN or by their short CN (`OWL Admins`). Safety measures: plain `ldap://`
without TLS is refused at start-up (only with the deliberate flag `OWL_SERVER_ALLOW_INSECURE_LDAP_WITHOUT_TLS=true`, see [](#insecure-switches)), the username is
**escaped** in the search filter (no LDAP injection), empty passwords never reach the server (they
would count as an "anonymous bind"), and a filter that matches more than one entry denies the login.
A local account of the same name is tried first.

### Reverse-proxy authentication: Kerberos / SPNEGO, SAML, oauth2-proxy, Authelia

Some protocols are best handled by a component built for them. OWL accepts an identity asserted by
the **reverse proxy in front of it**, so Kerberos (single sign-on from the Windows/AD desktop), SAML,
and any "forward auth" product all work without OWL speaking those protocols itself.

```ini
OWL_SERVER_PROXY_AUTH=true
OWL_SERVER_PROXY_SECRET_FILE=/run/secrets/proxy_secret     # >= 24 characters, shared with the proxy
# headers the proxy sets (these are the defaults):
OWL_SERVER_PROXY_USER_HEADER=X-Remote-User
OWL_SERVER_PROXY_GROUPS_HEADER=X-Remote-Groups
OWL_SERVER_PROXY_EMAIL_HEADER=X-Remote-Email
OWL_SERVER_PROXY_ADMIN_VALUES=EXAMPLE\owl-admins
```

**Trust model.** OWL believes the user headers *only* when the request also carries
`X-OWL-Proxy-Secret` with the shared secret. A client that merely sends `X-Remote-User: boss` is
ignored; a wrong secret is rejected with 401. The secret (not the source IP) is the trust anchor, so
it works behind any number of hops. **The proxy must overwrite or strip these headers** on incoming
requests.

Example: **Apache with Kerberos** (`mod_auth_gssapi`):

```apache
<Location "/">
    AuthType GSSAPI
    AuthName "OWL"
    GssapiCredStore keytab:/etc/apache2/owl.keytab
    Require valid-user
    RequestHeader unset X-Remote-User
    RequestHeader unset X-Remote-Groups
    RequestHeader set X-Remote-User "%{REMOTE_USER}s"
    RequestHeader set X-OWL-Proxy-Secret "…same secret…"
</Location>
ProxyPass / http://127.0.0.1:8080/
```

Groups for the mapping can come from the proxy (for example an Apache `mod_lookup_identity` or an
`X-Remote-Groups` set by oauth2-proxy/Authelia). SAML works the same way through Shibboleth or
`mod_auth_mellon`. Kerberos is therefore supported *through the proxy*; OWL does not link a GSSAPI
library itself.

### What is deliberately not built in

- native SAML and native Kerberos/GSSAPI (use the proxy pattern above);
- provisioning protocols such as SCIM;
- storing identity-provider secrets in the database: they come from the environment or `*_FILE`
  secrets, so they never travel through the browser.

## Which one should I choose?

| Situation | Suggestion |
| --- | --- |
| just me / a lab | stay open on localhost, or secure with one local admin |
| a small team | local accounts managed in the dashboard |
| a company with Keycloak/Entra/Okta | OIDC |
| Active Directory without SSO infrastructure | LDAP/AD |
| Windows desktops with Kerberos SSO | proxy authentication (Apache/IIS/nginx SPNEGO) |
| open source community with GitHub accounts | OAuth (GitHub) with an allow-list, or public registries + publishers as members |
