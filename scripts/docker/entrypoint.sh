#!/bin/sh
set -e

echo "Waiting for MariaDB at ${DB_HOST:-db}:${DB_PORT:-3306}..."
until mariadb-admin ping -h "${DB_HOST:-db}" -P "${DB_PORT:-3306}" -u "${DB_USER}" -p"${DB_PASSWORD}" --silent 2>/dev/null; do
  sleep 2
done
echo "MariaDB is up - applying migrations."

alembic upgrade head

exec "$@"
