#!/bin/sh

echo "Waiting for PostgreSQL to start..."

until pg_isready -h wallet_db -p 5432 -U "$WALLET_DB_USER"; do
  echo "Postgres is unavailable - sleeping..."
  sleep 1
done

echo "PostgreSQL started! Running database migrations..."

alembic upgrade head

echo "Migrations applied successfully! Starting Uvicorn server..."

# command for dockerfile
exec "$@"