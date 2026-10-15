#!/usr/bin/env bash
# Starts a fresh OWL Server (SQLite, open mode) for the browser tests.
set -euo pipefail
DIR="$(mktemp -d)"
trap 'rm -rf "$DIR"' EXIT
cd "$(dirname "$0")/../.."
export OWL_SERVER_DATABASE_URL="$DIR/e2e.sqlite3"
export OWL_SERVER_LOGIN_RATE_PER_MINUTE=1000
unset OWL_SERVER_ADMIN_TOKEN OWL_SERVER_OPEN
exec uv run owl-server serve --host 127.0.0.1 --port "${E2E_API_PORT:-18080}"
