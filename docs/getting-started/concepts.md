# Concepts

| Concept | Meaning |
| --- | --- |
| **Registry** | a named collection of skills with its own visibility (`public`/`private`) and members. The `default` registry is created automatically |
| **Skill version** | one immutable revision, addressed by its content hash. A changed upload becomes a *new* version and the current pointer moves; pushing an old, known version again is a rollback |
| **Open / secured** | a new server is **open** (no login) until it is secured in the dashboard – see {doc}`/guide/identity` |
| **Mode** | `public`, `private` or `mixed` (applies once secured) – see {doc}`/guide/access-and-roles` |
| **Roles** | `reader` < `publisher` < `admin`, evaluated **per registry** |
| **Principal** | who is calling: anonymous (open mode), bootstrap admin (environment token), a user (session or API token) or a service token |
| **Identity provider** | an external login source: OIDC, OAuth 2.0, LDAP/AD or a trusted reverse proxy |

A content hash covers `SKILL.md`, metadata and bundled files – not timestamps. It detects change; it is
**not** a signature and does not prove who wrote a skill.

The URL of a non-default registry is `<server>/r/<slug>`; the OWL CLI appends `/api/v1/…` itself:

```console
$ owl remote add team https://skills.example.com/r/team --token-env OWL_TOKEN
```
