# Backup and restore

All state lives in PostgreSQL, so a database backup is a complete backup.

```console
$ docker compose exec -T db pg_dump -U owl -Fc owl > owl-$(date +%F).dump
$ docker compose exec -T db pg_restore -U owl -d owl --clean < owl-2026-10-15.dump
```

Additionally, every registry can be exported as plain files in git-registry layout
(`GET /r/<slug>/api/v1/export`, or the *Export* action in the dashboard). That export is handy for
mirroring into a git registry but is not a replacement for a database backup, because users, tokens
and the audit log are not part of it.

Test the restore regularly, and back up **before** every upgrade: migrations run on start.
