#!/usr/bin/env sh
set -eu

echo "Running release migrations..."
if ! python -m alembic upgrade head; then
  echo "Release migration failed; application rollout must stop. Inspect the migration error and restore the previous application image." >&2
  exit 1
fi
echo "Release migrations completed. Start application replicas without running migrations."
