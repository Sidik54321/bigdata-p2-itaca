#!/bin/bash
# Script de inicialización de PostgreSQL: crea el usuario de solo lectura de
# la ingesta con las credenciales de .env.
set -e

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
    CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
    GRANT CONNECT ON DATABASE $POSTGRES_DB TO $DB_USER;
    GRANT USAGE ON SCHEMA public TO $DB_USER;
    GRANT SELECT ON alumnos, contenidos, calificaciones, cursos, grupos TO $DB_USER;
EOSQL
