#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Setting up LinkFinder symlink..."
echo "Starting application..."
exec "$@"
