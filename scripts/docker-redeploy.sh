#!/usr/bin/env bash
# One-click Docker redeploy for local development.
#
# Stops the current Docker stack, optionally cleans build artifacts,
# rebuilds the open_notebook image from local source via docker-compose.build.yml,
# and brings the stack back up.
#
# Run from anywhere — the script resolves the repo root from its own path.

set -euo pipefail

COMPOSE_FILE="docker-compose.build.local.yml"
SERVICE="open_notebook"
NO_CACHE=0
CLEAN=0
FOLLOW_LOGS=0

usage() {
  cat <<EOF
Usage: $0 [options]

Stops the current Docker stack, rebuilds the ${SERVICE} image, and brings
the stack back up using ${COMPOSE_FILE}.

Options:
  --no-cache     Force a clean rebuild without using Docker's build cache.
                 Use after editing Dockerfile, dependencies, or when a
                 cached layer is masking your changes.
  --clean        --no-cache + also remove frontend/.next and the old
                 ${SERVICE} image. Slowest, but guaranteed fresh.
  --logs         After bringing the stack up, tail logs (Ctrl+C to detach).
  -h, --help     Show this help.

Examples:
  $0                       # quick redeploy (uses cache)
  $0 --no-cache            # rebuild from scratch
  $0 --clean --logs        # nuclear option + watch logs
EOF
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache) NO_CACHE=1; shift ;;
    --clean)    CLEAN=1; NO_CACHE=1; shift ;;
    --logs)     FOLLOW_LOGS=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; echo; usage; exit 1 ;;
  esac
done

# Move to repo root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Error: $COMPOSE_FILE not found in $REPO_ROOT" >&2
  exit 1
fi

echo "==> Repo:         $REPO_ROOT"
echo "==> Compose file: $COMPOSE_FILE"
echo

echo "==> Stopping running stack..."
docker compose -f "$COMPOSE_FILE" down

if [[ "$CLEAN" -eq 1 ]]; then
  echo
  echo "==> Cleaning frontend/.next ..."
  rm -rf frontend/.next || true

  echo "==> Removing old ${SERVICE} images (if any) ..."
  # docker compose image names take the form "<project>-<service>" or
  # "<project>_<service>" depending on compose version. Both are tried.
  docker image rm "open-notebook-${SERVICE}" 2>/dev/null || true
  docker image rm "open_notebook-${SERVICE}" 2>/dev/null || true
fi

echo
# --progress=plain prints the full build output instead of the collapsed
# TUI summary, which is essential for diagnosing npm/tsc/eslint failures
# in the frontend layer.
if [[ "$NO_CACHE" -eq 1 ]]; then
  echo "==> Building ${SERVICE} image (--no-cache) ..."
  docker compose -f "$COMPOSE_FILE" build --no-cache --progress=plain "$SERVICE"
else
  echo "==> Building ${SERVICE} image (using cache) ..."
  docker compose -f "$COMPOSE_FILE" build --progress=plain "$SERVICE"
fi

echo
echo "==> Starting stack..."
docker compose -f "$COMPOSE_FILE" up -d

echo
echo "==> Done. Service URLs:"
echo "    UI:        http://localhost:8502"
echo "    API docs:  http://localhost:5055/docs"
echo "    SurrealDB: ws://localhost:8000/rpc"

if [[ "$FOLLOW_LOGS" -eq 1 ]]; then
  echo
  echo "==> Tailing logs (Ctrl+C to stop) ..."
  docker compose -f "$COMPOSE_FILE" logs -f --tail=50
fi
