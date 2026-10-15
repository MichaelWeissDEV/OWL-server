# Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| Start-up aborts with `ConfigError` | the message names the variable; secrets must be long enough, endpoints `https://`, and `ldap://` needs StartTLS |
| `OWL_SERVER_ALLOW_INSECURE_…` warning in the log | an insecure switch is active on purpose; remove it unless you are in a lab |
| Warning `OPEN MODE` | the server is not secured yet – use Settings → Secure this server, or set `OWL_SERVER_OPEN=false` |
| `401` from the CLI | the server is secured: create a token and use `--token-env` |
| `403` | your role in that registry is too low (reader < publisher < admin) |
| `404` for a private registry | also returned when you have no access, on purpose |
| `413` on push | raise `OWL_SERVER_MAX_BODY_MB` and the proxy's body limit |
| LDAP login fails | check `LDAP_USER_FILTER`, the service account, and that the TLS certificate is trusted (`LDAP_CA_FILE`) |
| Wrong client IP in the audit log | set `FORWARDED_ALLOW_IPS` to your proxy |
| `/ready` fails | the database is unreachable or not migrated; check `docker compose logs api` |
