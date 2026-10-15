# Security

OWL Server is **alpha** software. This page lists what it does and what you must do yourself.

## What the server does

- Authorization is checked on the server for every request; the dashboard is never a security boundary.
- Passwords use Argon2id; API tokens are stored as hashes and shown once.
- Sessions are bearer tokens (no cookies), so there is no CSRF surface.
- Request bodies are size limited, login attempts are rate limited, security headers are set, the
  audit log records administrative actions.
- External identities never take over local accounts of the same name.
- JWTs from OIDC providers are accepted only with asymmetric algorithms.
- The container runs as a non-root user with a read-only file system; the dashboard container serves a strict
  Content-Security-Policy.

## What you must do

- **Secure the server** (dashboard → Settings) before anyone but you can reach it. Open mode is a
  deliberate default for first steps, not for production.
- Put TLS in front ({doc}`reverse-proxy`) and back up PostgreSQL ({doc}`backup`).
- Keep secrets out of version control; every secret variable also supports a `…_FILE` variant.
- Do not enable any `ALLOW_INSECURE_…` switch outside a lab ({ref}`insecure-switches`).

## Insecure switches

Everything that weakens security exists only as a switch with a long, deliberate name, is absent from
every default configuration and is logged as a warning at start-up. Full list: {ref}`insecure-switches`.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting
for the repository, or contact the maintainer directly.
