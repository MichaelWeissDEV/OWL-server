# OpenID Connect (optional)

OWL Server can sign users in through an external identity provider (IdP) such as **Keycloak** or any
OIDC-compliant service. It is switched off unless `OWL_SERVER_OIDC_ISSUER` is set, and it does not affect
the OWL CLI's local use in any way.

## What is implemented

- **OIDC discovery** (`/.well-known/openid-configuration`; the `issuer` must match the configuration),
- **authorization code flow with PKCE** (S256), a random `state` and `nonce` per attempt, single use and
  expiring after 10 minutes,
- ID token validation with **PyJWT**: signature via the IdP's **JWKS** (refetched once on an unknown key,
  so key rotation works), **issuer**, **audience**, `exp`/`iat` (60 s leeway), required claims, **nonce**,
  `azp` for multi-audience tokens. Only asymmetric algorithms (`RS*`, `ES*`, `PS*`) are accepted –
  `none` and HMAC are refused,
- **role mapping** from a claim, user creation on first login, and a normal OWL session token as the result.

It is not a hand-written OAuth stack: the protocol steps are explicit and covered by tests with a mocked
IdP (real RSA signatures).

## Configuration

| Variable | Meaning |
| --- | --- |
| `OWL_SERVER_OIDC_ISSUER` | issuer URL, **https** (e.g. `https://id.example.com/realms/owl`) |
| `OWL_SERVER_OIDC_CLIENT_ID` | client id registered at the IdP |
| `OWL_SERVER_OIDC_CLIENT_SECRET` | client secret for a confidential client (use `_FILE`) |
| `OWL_SERVER_OIDC_REDIRECT_URI` | where the IdP sends the browser back; must be registered at the IdP |
| `OWL_SERVER_OIDC_SCOPES` | default `openid profile email` |
| `OWL_SERVER_OIDC_AUDIENCE` | expected `aud` (default: the client id) |
| `OWL_SERVER_OIDC_USERNAME_CLAIM` | default `preferred_username` (falls back to `email`, then `sub`) |
| `OWL_SERVER_OIDC_ROLE_CLAIM` | claim with groups/roles, e.g. `groups` |
| `OWL_SERVER_OIDC_ADMIN_VALUES` | comma separated values of that claim that make a user a **server admin** |
| `OWL_SERVER_OIDC_REGISTRY_ROLES` | JSON: `{"owl-publishers": {"team": "publisher"}, "owl-readers": {"team": "reader"}}` |

### Keycloak example

1. Create a realm `owl` and a **confidential** client `owl-server` with *Standard flow* enabled and the
   redirect URI of your dashboard (for example `https://skills.example.com/auth/callback`).
2. Add a *Group Membership* mapper to the client scope so the ID token contains `groups`.
3. Configure:

```ini
OWL_SERVER_OIDC_ISSUER=https://id.example.com/realms/owl
OWL_SERVER_OIDC_CLIENT_ID=owl-server
OWL_SERVER_OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc_secret
OWL_SERVER_OIDC_REDIRECT_URI=https://skills.example.com/auth/callback
OWL_SERVER_OIDC_ROLE_CLAIM=groups
OWL_SERVER_OIDC_ADMIN_VALUES=owl-admins
OWL_SERVER_OIDC_REGISTRY_ROLES={"owl-publishers": {"team": "publisher"}}
```

## The flow

```{mermaid}
sequenceDiagram
    participant B as Browser / dashboard
    participant S as OWL Server
    participant I as Identity provider
    B->>S: GET /api/v1/auth/oidc/login?json=1
    S->>S: store state, nonce, PKCE verifier
    S-->>B: authorization_url
    B->>I: authorize (code_challenge, state, nonce)
    I-->>B: redirect to REDIRECT_URI?code&state
    B->>S: POST /api/v1/auth/oidc/exchange {code, state}
    S->>I: token request (code + code_verifier)
    I-->>S: id_token
    S->>S: validate signature, iss, aud, exp, nonce
    S-->>B: OWL session token
```

`GET /api/v1/auth/oidc/callback?code&state` does the same for server-side redirects.

## Account handling

- Users are matched by the IdP's `sub`; a username clash with a local account gets the suffix `@oidc`.
- Group memberships and the admin flag are **re-synchronised on every login**: removing someone from an IdP
  group removes the access at their next login (existing sessions expire after `SESSION_TTL_HOURS`; disable
  the user to cut them immediately).
- Accounts managed by the IdP have no password in OWL.
- Disabled users are refused (403).

## Troubleshooting

| Message | Cause |
| --- | --- |
| `The identity provider is not reachable` (502) | discovery/JWKS/token endpoint unreachable – network, DNS, TLS |
| `The identity provider is misconfigured` (502) | the discovery document's `issuer` differs from `OIDC_ISSUER`, or endpoints are missing |
| `The ID token is not valid` (401) | wrong issuer/audience/signature or an expired token; check the client id and clock |
| `The ID token does not belong to this login` (401) | nonce mismatch (a replayed or foreign token) |
| `The login attempt is unknown or was already used` (401) | state replayed or expired (10 min) |

Details are in the server log and audit log (`auth.oidc_failed`); responses never include internals.
