#!/bin/sh
# Start as root only long enough to make the data directory writable, then drop to the unprivileged app user.
# Needed because a mounted volume (Railway, `docker run -v`) arrives owned by root, while the app runs as uid 10001.
set -e
DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR" /app/.cache
if [ "$(id -u)" = "0" ]; then
  chown -R 10001:10001 "$DATA_DIR" /app/.cache
  exec setpriv --reuid=10001 --regid=10001 --clear-groups "$@"
fi
exec "$@"
