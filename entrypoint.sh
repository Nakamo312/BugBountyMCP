#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Setting up LinkFinder symlink..."
if [ -f "/opt/linkfinder/lf_env/bin/linkfinder" ]; then
    sudo ln -sf /opt/linkfinder/lf_env/bin/linkfinder /usr/local/bin/linkfinder 2>/dev/null || true
    echo "LinkFinder symlink created in /usr/local/bin"
fi

echo "Starting application..."
exec "$@"
