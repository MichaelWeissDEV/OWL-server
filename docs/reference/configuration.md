# Server configuration

All settings are environment variables with the prefix `OWL_SERVER_`. Each can also be given as
`OWL_SERVER_<NAME>_FILE` (path of a file containing the value). The configuration is validated at start;
`owl-server check-config` validates without starting.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | **required** | `postgresql://user:password@host/db` (mapped to psycopg 3). SQLite paths work for tests |
| `MODE` | `mixed` | `public`, `private` or `mixed` ({doc}`/guide/access-and-roles`) |
| `DEFAULT_REGISTRY` | `default` | slug of the registry served at `/api/v1/…` (created automatically) |
| `OPEN` | automatic | `true` = always open (no login), `false` = always secured, unset = open until secured ({doc}`/guide/identity`) |
| `ADMIN_TOKEN` | – | optional bootstrap administrator token, **at least 24 characters**; setting it secures the server |
| `LOCAL_ACCOUNTS` | `true` | password logins and user management in the dashboard |
| `AUTO_MIGRATE` | `true` | apply Alembic migrations at start |
| `MAX_BODY_MB` | `40` | request body limit (a skill may be 20 MiB; uploads are base64) |
| `SESSION_TTL_HOURS` | `12` | lifetime of login sessions |
| `LOGIN_RATE_PER_MINUTE` | `10` | attempts per minute and client for login endpoints |
| `CORS_ORIGINS` | – | comma separated origins allowed to call the API from a browser (for the dashboard) |
| `PUBLIC_URL` | – | the external URL (informational) |
| `OIDC_*` | – | OpenID Connect, see {doc}`/guide/oidc` |
| `OAUTH_*` | – | OAuth 2.0 / GitHub, see {doc}`/guide/identity` |
| `LDAP_*` | – | LDAP / Active Directory, see {doc}`/guide/identity` |
| `PROXY_*` | – | proxy authentication (Kerberos/SAML), see {doc}`/guide/identity` |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | proxies whose `X-Forwarded-*` headers are trusted (uvicorn) |

The CLI: `owl-server serve|migrate|check-config|create-admin|create-token`.

## Choosing the mode

The mode applies to a **secured** server; while the server is open everybody has full access
({doc}`/guide/identity`).

| Mode | Effect |
| --- | --- |
| `public` | every registry is public: anyone can read; writes still need rights |
| `private` | every registry is private: nothing is readable without authentication |
| `mixed` | each registry has its own visibility (default for new registries: `private`) |

The mode is enforced when registries are created or changed and when they are read, so a registry cannot
be made more open than the mode allows.


(insecure-switches)=
## Insecure switches

Secure behaviour is the default and has no setting. Everything that *weakens* security exists only
as a switch with a deliberately long name that is not part of any default configuration. Whoever
sets one makes a conscious decision, and every active switch is logged as a **warning** at start-up.

| Variable (all `OWL_SERVER_…`, value `true`) | What it allows |
| --- | --- |
| `ALLOW_INSECURE_LDAP_WITHOUT_TLS` | plain `ldap://` without StartTLS: **passwords travel unencrypted** |
| `ALLOW_INSECURE_OIDC_OVER_HTTP` | an OIDC issuer that is not `https://` |
| `ALLOW_INSECURE_OAUTH_OVER_HTTP` | OAuth endpoints that are not `https://` |
| `ALLOW_INSECURE_DISABLE_OIDC_TLS_VERIFICATION` | do not verify the OIDC server certificate |
| `ALLOW_INSECURE_DISABLE_OAUTH_TLS_VERIFICATION` | do not verify the OAuth server certificate |
| `ALLOW_INSECURE_DISABLE_LDAP_TLS_VERIFICATION` | do not verify the LDAP server certificate |

```{warning}
These switches are meant for labs and tests only. With them an attacker on the network can read
passwords and tokens or impersonate your identity provider. Prefer fixing the cause: use `https://`,
`ldaps://` or StartTLS, and add your CA with `OWL_SERVER_LDAP_CA_FILE` instead of disabling verification.
```

Setting the old `…_VERIFY_TLS=false` is refused with a message that names the matching long flag.
The open default (no access restriction until you secure the server) is a separate, documented
choice, see {doc}`Open mode </guide/identity>`.
