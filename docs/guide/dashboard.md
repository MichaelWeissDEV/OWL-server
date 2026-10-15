# Web dashboard

The dashboard is an **optional** web interface for the server. Everything it does goes through the
documented HTTP API - it never touches the database - and the CLI keeps working without it.

```console
$ docker compose --profile dashboard up -d --build      # http://127.0.0.1:8080
```

It is a separate container (nginx serving the static build, forwarding `/api/…` and
`/r/<registry>/api/…` to the API), so the API does not depend on it. For development:
`cd dashboard && npm ci && npm run dev` (proxies to `OWL_API`, default `http://127.0.0.1:8765`).

## What you can do

| Area | Functions |
| --- | --- |
| **Overview** | registries, counts, top tags, recent versions |
| **Skills** | search (text, author, tags), paging, detail with rendered `SKILL.md`, files (text preview, binary download), **versions**, **compare** two versions (line diff), download as zip, **add** (write `SKILL.md`, upload a file or a zip), **edit** (creates a new version), restore an old version, delete |
| **Collections** | create, add/remove skills |
| **Activity** | newest versions with author and hash |
| **Registries** | create (public/private), rename, members and roles, export as git registry, delete |
| **Users** *(admin)* | create, disable, make admin, reset password, registry memberships, delete; shows where each account comes from (local, OIDC, LDAP, ...) |
| **Service tokens** *(admin)* | create tokens for CI (shown once), revoke |
| **Audit log** *(admin)* | sign-ins, uploads, changes with filters |
| **Settings** *(admin)* | open/secured state and the **Secure this server** wizard, enabled sign-in methods, server info |
| **Profile** | change password, personal API tokens |

Light and dark mode (follows the system setting, switchable), responsive layout down to phones,
keyboard operable with a skip link, labelled controls and clear loading, error and empty states.

## Security properties

- **The browser is not a security boundary.** Buttons are hidden by role, but the server checks every
  request; the tests assert that a reader's token gets `403` from the admin API.
- **Skill content is untrusted.** Markdown is rendered without raw HTML, sanitised a second time,
  images are not loaded and links are limited to `http(s)`/`mailto` with `noopener`. Text files are
  shown as plain text, binary files are downloads. (Covered by component and browser tests with
  script/`onerror`/`javascript:` payloads.)
- **Sessions** are bearer tokens kept in `sessionStorage` (gone when the tab closes), so there are no
  cookies and no CSRF surface. A 401 ends the session everywhere.
- **Secrets** are shown once (tokens) and never listed; identity-provider secrets are configured on
  the server, not in the browser.
- The container serves a strict **Content-Security-Policy** (own scripts only, no framing),
  `nosniff`, `no-referrer`, runs as an unprivileged user with a read-only file system.

## First run

1. Start the stack. The server is **open**: open the dashboard, no login.
2. *Registries → New registry*, then add skills (or push with the OWL CLI).
3. *Settings → Secure this server*: choose an administrator name and password - you are signed in and
   sign-in is required from now on.
4. *Users → New user*, give them a role in a registry under *Registries → <name> → Members*.
5. Later: connect an identity provider ({doc}`/guide/identity`).

## Single sign-on in the dashboard

Configure the redirect URI of your provider as `https://<your host>/auth/callback`. The login page
shows one button per configured provider (OIDC, OAuth), the password form when local accounts or LDAP
are enabled; with proxy authentication nothing is needed - the proxy signs users in.
