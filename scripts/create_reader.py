"""Provision the application role without printing or shell-interpolating passwords."""

import os

import psycopg
from psycopg import sql

from itadb.config import Settings


def main() -> None:
    password = os.environ["API_DB_PASSWORD"]
    if len(password) < 12:
        raise ValueError("API_DB_PASSWORD must contain at least 12 characters")
    with psycopg.connect(Settings().admin_database_url) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='itadb_reader'").fetchone():
            connection.execute("CREATE ROLE itadb_reader LOGIN")
        connection.execute(
            sql.SQL(
                "ALTER ROLE itadb_reader PASSWORD {} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION"
            ).format(sql.Literal(password))
        )
        connection.execute("ALTER ROLE itadb_reader SET default_transaction_read_only=on")
        connection.execute("ALTER ROLE itadb_reader SET statement_timeout='5s'")
        connection.execute("ALTER ROLE itadb_reader SET idle_in_transaction_session_timeout='10s'")
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT USAGE ON SCHEMA api TO itadb_reader")
        connection.execute("GRANT SELECT ON ALL TABLES IN SCHEMA api TO itadb_reader")
        connection.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO itadb_reader"
        )


if __name__ == "__main__":
    main()
