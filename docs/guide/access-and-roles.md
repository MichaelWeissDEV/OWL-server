# Authentication, roles and access control

Reading and writing are **separate permissions**, evaluated on the server for every request. A client or
dashboard is never a security boundary.

```{note}
This page describes a **secured** server. A new server is *open* - no authentication, everybody is an
administrator - until it is secured; see {doc}`/guide/identity`, which also covers LDAP/Active Directory,
OAuth 2.0 and Kerberos/SAML through a proxy.
```

## Who is calling

| Principal | How it authenticates | Rights |
| --- | --- | --- |
| open | no `Authorization` header while the server is **open** | everything (administrator) |
| anonymous | no `Authorization` header on a secured server | read **public** registries only |
| bootstrap admin | `Authorization: Bearer <OWL_SERVER_ADMIN_TOKEN>` | everything (compared in constant time) |
| user | login session or personal API token | per registry via membership; `is_admin` users may do everything |
| service token | API token without a user, limited to **one registry** | exactly the token's role in that registry |

Invalid, expired or revoked tokens are answered with 401 – they are never treated as "anonymous".

## Roles (per registry)

| Role | May |
| --- | --- |
| `reader` | read skills, versions, stats, collections; download |
| `publisher` | + upload/update/delete skills, manage collections |
| `admin` | + rename the registry, manage its members |

Server administrators additionally create/delete registries, change visibility, manage users and service
tokens and read the audit log.

## Visibility and what outsiders learn

| Caller | Private registry | Public registry |
| --- | --- | --- |
| anonymous | **401** (asked to log in – also for registries that do not exist) | read |
| authenticated, no access | **404** (the same answer as for a registry that does not exist) | read |
| authenticated with a role | as role | as role |

Private skills are never listed in another registry's search or facets, and registry listings
(`GET /api/v1/registries`) show only what the caller may see.

## Tokens

- **Service tokens** (`owl-server create-token` or `POST /api/v1/admin/tokens`): for CI and automation,
  limited to one registry, with a role and an optional lifetime.
- **Personal tokens** (`POST /api/v1/auth/tokens`, requires a password login): can be limited to a
  registry; their role can **never exceed the user's own rights**; a token cannot create more tokens.
  A personal token additionally *caps* its user: an admin's `reader` token is read-only.
- Tokens look like `owl_<random>`; only a SHA-256 of the secret is stored. The secret is shown once;
  listings show a short prefix. Tokens can be revoked and expire.

## Local accounts (optional)

On by default (`OWL_SERVER_LOCAL_ACCOUNTS`). Create the first administrator in the dashboard
(Settings → Secure this server) or with `owl-server create-admin NAME`.

- Passwords are hashed with **Argon2id**; at least 12 characters, not purely lower-case letters.
  Verification takes the same work for unknown users (no user enumeration). Hashes are upgraded when the
  parameters change.
- `POST /api/v1/auth/login` returns a **session token** (Bearer, default 12 h). There are no cookies, so
  there is no CSRF surface; the dashboard keeps the token in memory.
- Changing the password, disabling a user or removing sessions revokes all of the user's sessions.
- Login endpoints are **rate limited** (default 10/min per client and per username) and answer 429 with
  `Retry-After`. Failed logins are audited.
- Admins cannot remove their own administrator rights.

## Audit log

`GET /api/v1/admin/audit` (server admins) lists logins and failures, token creation/revocation, user and
registry changes, uploads (with the content hash) and deletions: time, actor, action, target, IP. It never
contains secrets, passwords or `Authorization` headers.

## Other protections

- request bodies are limited (`MAX_BODY_MB`), also while streaming (HTTP 413);
- uploaded skills are validated with the same rules as the CLI (names, size limits, **no unsafe file
  paths**, reserved names);
- security headers (`nosniff`, `X-Frame-Options: DENY`, no referrer); error responses never include stack
  traces;
- Markdown/HTML in skills is **data**: the API returns JSON only. A client that renders it must sanitise it.
