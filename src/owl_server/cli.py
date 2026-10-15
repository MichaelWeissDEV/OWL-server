"""``owl-server``: run the server and manage it from the command line."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from owl_server import __version__, accounts, db
from owl_server import models as m
from owl_server.config import ConfigError, load_settings


def _settings():  # type: ignore[no-untyped-def]
    try:
        return load_settings()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from owl_server.app import create_app

    settings = _settings()
    app = create_app(settings)
    if (
        settings.mode != "private"
        and not settings.admin_token
        and not settings.local_accounts
        and not settings.oidc
    ):
        print(
            "warning: no admin token, local accounts or OIDC configured - the server is read-only",
            file=sys.stderr,
        )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        proxy_headers=args.proxy_headers,
        forwarded_allow_ips=args.forwarded_allow_ips if args.proxy_headers else None,
    )
    return 0


def cmd_migrate(_args: argparse.Namespace) -> int:
    settings = _settings()
    db.upgrade(settings.database_url)
    engine = db.make_engine(settings.database_url)
    print(f"database is at revision {db.current_revision(engine)}")
    return 0


def cmd_check_config(_args: argparse.Namespace) -> int:
    settings = _settings()
    print(
        f"ok: mode={settings.mode} default_registry={settings.default_registry} "
        f"local_accounts={settings.local_accounts} oidc={'yes' if settings.oidc else 'no'} "
        f"admin_token={'set' if settings.admin_token else 'not set'}"
    )
    return 0


def cmd_create_admin(args: argparse.Namespace) -> int:
    settings = _settings()
    db.upgrade(settings.database_url)
    engine = db.make_engine(settings.database_url)
    password = args.password or getpass.getpass("Password: ")
    with db.session_scope(db.make_session_factory(engine)) as session:
        try:
            user = accounts.create_user(session, args.username, password, is_admin=True)
        except accounts.AccountError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"created administrator '{user.username}'")
    if not settings.local_accounts:
        print("note: set OWL_SERVER_LOCAL_ACCOUNTS=true to allow password logins", file=sys.stderr)
    return 0


def cmd_create_token(args: argparse.Namespace) -> int:
    settings = _settings()
    db.upgrade(settings.database_url)
    engine = db.make_engine(settings.database_url)
    with db.session_scope(db.make_session_factory(engine)) as session:
        registry = session.scalar(select(m.Registry).where(m.Registry.slug == args.registry))
        if registry is None:
            print(f"error: registry '{args.registry}' does not exist", file=sys.stderr)
            return 1
        try:
            secret, row = accounts.create_token(
                session, name=args.name, role=args.role, registry=registry, ttl_hours=args.ttl_hours
            )
        except accounts.AccountError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(secret)
        print(
            f"(token {row.prefix}... for registry '{args.registry}', role {args.role}; "
            "it is shown only once)",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="owl-server", description="OWL Server")
    parser.add_argument("--version", action="version", version=f"owl-server {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--proxy-headers", action="store_true", help="trust X-Forwarded-* from a reverse proxy"
    )
    serve.add_argument("--forwarded-allow-ips", default="127.0.0.1")
    serve.set_defaults(func=cmd_serve)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(func=cmd_migrate)
    sub.add_parser("check-config", help="validate the environment").set_defaults(
        func=cmd_check_config
    )
    admin = sub.add_parser("create-admin", help="create a local administrator account")
    admin.add_argument("username")
    admin.add_argument("--password", help="(prefer the prompt: arguments are visible in `ps`)")
    admin.set_defaults(func=cmd_create_admin)
    token = sub.add_parser("create-token", help="create a registry-scoped service token")
    token.add_argument("registry")
    token.add_argument("--role", choices=("reader", "publisher", "admin"), default="publisher")
    token.add_argument("--name", default="cli token")
    token.add_argument("--ttl-hours", type=float)
    token.set_defaults(func=cmd_create_token)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
