#!/usr/bin/env python3
"""ORCA PostgreSQL Database Setup.

Creates the PostgreSQL database, user, schema, tables, and indexes
required by the ORCA HITL feedback pipeline.

Usage:
    # Interactive (prompts for connection details):
    python setup_db.py

    # Using environment variables:
    ORCA_PG_HOST=localhost ORCA_PG_PORT=5432 \
    ORCA_PG_USER=orca ORCA_PG_PASSWORD=secret \
    ORCA_PG_DATABASE=orca_feedback python setup_db.py

    # Command-line arguments:
    python setup_db.py --host localhost --port 5432 \
        --user orca --password secret --database orca_feedback

    # Only create tables (skip DB/user creation — useful when DB exists):
    python setup_db.py --tables-only

    # Drop and recreate everything (DESTRUCTIVE):
    python setup_db.py --reset

    # Migrate existing SQLite data into PostgreSQL:
    python setup_db.py --migrate-from ./orca_feedback.db
"""

import argparse
import json
import os
import sys
import logging

logger = logging.getLogger("orca.setup_db")

# ── SQL Statements ────────────────────────────────────────────────────────

SCHEMA_NAME = "orca"

CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME};"

CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.compliance_decisions (
    id              SERIAL PRIMARY KEY,
    project         VARCHAR(255) NOT NULL,
    file_path       TEXT NOT NULL,
    rule_id         VARCHAR(255) NOT NULL,
    violation_text  TEXT,
    decision        VARCHAR(50) NOT NULL,
    constraints     TEXT,
    reviewer        VARCHAR(255),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence      REAL DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
"""

CREATE_INDEXES = [
    f"CREATE INDEX IF NOT EXISTS idx_cd_rule_id    ON {SCHEMA_NAME}.compliance_decisions (rule_id);",
    f"CREATE INDEX IF NOT EXISTS idx_cd_file_path  ON {SCHEMA_NAME}.compliance_decisions (file_path);",
    f"CREATE INDEX IF NOT EXISTS idx_cd_project    ON {SCHEMA_NAME}.compliance_decisions (project);",
    f"CREATE INDEX IF NOT EXISTS idx_cd_rule_file  ON {SCHEMA_NAME}.compliance_decisions (rule_id, file_path);",
    f"CREATE INDEX IF NOT EXISTS idx_cd_timestamp  ON {SCHEMA_NAME}.compliance_decisions (timestamp DESC);",
    f"CREATE INDEX IF NOT EXISTS idx_cd_decision   ON {SCHEMA_NAME}.compliance_decisions (decision);",
]

DROP_TABLE = f"DROP TABLE IF EXISTS {SCHEMA_NAME}.compliance_decisions CASCADE;"
DROP_SCHEMA = f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE;"

# Decision-type CHECK (applied as ALTER so the table creation stays clean)
ADD_DECISION_CHECK = f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_decision_type'
    ) THEN
        ALTER TABLE {SCHEMA_NAME}.compliance_decisions
        ADD CONSTRAINT chk_decision_type
        CHECK (decision IN ('FIX','SKIP','WAIVE','FIX_WITH_CONSTRAINTS','NEEDS_REVIEW','UPSTREAM_EXCEPTION'));
    END IF;
END $$;
"""

# ── Helpers ───────────────────────────────────────────────────────────────

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def get_connection_params(args) -> dict:
    """Resolve connection parameters: CLI > env > defaults."""
    return {
        "host":     args.host     or _env("ORCA_PG_HOST", "localhost"),
        "port":     int(args.port or _env("ORCA_PG_PORT", "5432")),
        "user":     args.user     or _env("ORCA_PG_USER", "orca"),
        "password": args.password or _env("ORCA_PG_PASSWORD", ""),
        "database": args.database or _env("ORCA_PG_DATABASE", "orca_feedback"),
    }


def _connect(params: dict, database: str = None):
    """Return a psycopg2 connection. Overrides database if provided."""
    import psycopg2
    cp = dict(params)
    if database is not None:
        cp["database"] = database
    conn = psycopg2.connect(**cp)
    conn.autocommit = True
    return conn


def check_psycopg2():
    """Ensure psycopg2 is installed; give a helpful message if not."""
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("ERROR: psycopg2 is not installed.")
        print("Install it with:")
        print("  pip install psycopg2-binary")
        print("  # or for production:")
        print("  pip install psycopg2")
        sys.exit(1)


def check_pg_server(params: dict) -> bool:
    """Check that PostgreSQL is reachable; print install/start help if not."""
    import psycopg2

    # Try the target database first, then 'postgres' as fallback
    for db in [params["database"], "postgres"]:
        try:
            conn = psycopg2.connect(
                host=params["host"],
                port=params["port"],
                user=params["user"],
                password=params["password"],
                database=db,
                connect_timeout=5,
            )
            conn.close()
            return True
        except psycopg2.OperationalError:
            continue

    # Connection failed — print platform-specific help
    print()
    print("  ERROR: Cannot connect to PostgreSQL at "
          f"{params['host']}:{params['port']}")
    print()
    print("  PostgreSQL must be installed and running before setup.")
    print()
    print("  ── macOS (Homebrew) ────────────────────────────────────")
    print("    brew install postgresql@16")
    print("    brew services start postgresql@16")
    print()
    print("  ── macOS (Postgres.app) ────────────────────────────────")
    print("    Download from https://postgresapp.com and start it.")
    print()
    print("  ── Ubuntu / Debian ─────────────────────────────────────")
    print("    sudo apt update && sudo apt install postgresql")
    print("    sudo systemctl start postgresql")
    print()
    print("  ── RHEL / Fedora ───────────────────────────────────────")
    print("    sudo dnf install postgresql-server postgresql")
    print("    sudo postgresql-setup --initdb")
    print("    sudo systemctl start postgresql")
    print()
    print("  ── Or use the bootstrap script ─────────────────────────")
    print("    python bootstrap_db.py")
    print("    (auto-installs PostgreSQL, starts it, creates user/db)")
    print()
    print("  After PostgreSQL is running, create the ORCA user/db:")
    print(f"    createuser -s {params['user']}")
    print(f"    createdb -O {params['user']} {params['database']}")
    print()
    print("  Then re-run this script:")
    print(f"    python setup_db.py --host {params['host']} "
          f"--user {params['user']} --database {params['database']}")
    print()
    return False


# ── Core Setup Functions ──────────────────────────────────────────────────

def create_database(params: dict):
    """Create the target database if it does not exist."""
    import psycopg2
    db_name = params["database"]

    # Connect to the default 'postgres' database to issue CREATE DATABASE
    try:
        conn = _connect(params, database="postgres")
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
        if cur.fetchone():
            print(f"  Database '{db_name}' already exists.")
        else:
            cur.execute(f'CREATE DATABASE "{db_name}";')
            print(f"  Created database '{db_name}'.")

        cur.close()
        conn.close()
    except psycopg2.OperationalError as e:
        # If we can't connect to 'postgres', the DB server may require
        # the target database to already exist. Fall through gracefully.
        logger.warning(f"Could not connect to 'postgres' DB: {e}")
        print(f"  Skipping database creation (connect to 'postgres' failed).")
        print(f"  Make sure '{db_name}' exists before continuing.\n")


def create_schema_and_tables(params: dict):
    """Create schema, table, indexes, and constraints."""
    conn = _connect(params)
    cur = conn.cursor()

    cur.execute(CREATE_SCHEMA)
    print(f"  Schema '{SCHEMA_NAME}' ready.")

    cur.execute(CREATE_TABLE)
    print(f"  Table '{SCHEMA_NAME}.compliance_decisions' ready.")

    for idx_sql in CREATE_INDEXES:
        cur.execute(idx_sql)
    print(f"  Indexes created ({len(CREATE_INDEXES)}).")

    cur.execute(ADD_DECISION_CHECK)
    print("  Decision-type CHECK constraint applied.")

    cur.close()
    conn.close()


def reset_database(params: dict):
    """Drop and recreate schema (DESTRUCTIVE)."""
    conn = _connect(params)
    cur = conn.cursor()

    cur.execute(DROP_TABLE)
    cur.execute(DROP_SCHEMA)
    print("  Dropped existing schema and tables.")

    cur.close()
    conn.close()

    create_schema_and_tables(params)


def verify_setup(params: dict) -> bool:
    """Run a quick smoke test: insert, query, delete a test row."""
    conn = _connect(params)
    cur = conn.cursor()

    try:
        cur.execute(f"""
            INSERT INTO {SCHEMA_NAME}.compliance_decisions
                (project, file_path, rule_id, violation_text, decision, confidence)
            VALUES ('__setup_test__', 'test.c', 'TEST_001', 'setup verification', 'SKIP', 0.99)
            RETURNING id;
        """)
        row_id = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.compliance_decisions WHERE id = %s;", (row_id,))
        count = cur.fetchone()[0]
        assert count == 1, "Verification insert not found"

        cur.execute(f"DELETE FROM {SCHEMA_NAME}.compliance_decisions WHERE id = %s;", (row_id,))
        print("  Verification passed: insert → query → delete OK.")
        return True

    except Exception as e:
        print(f"  Verification FAILED: {e}")
        return False

    finally:
        cur.close()
        conn.close()


def print_connection_info(params: dict):
    """Print a summary of what to put in config.yaml."""
    masked_pw = "***" if params["password"] else "(none)"
    print("\n  Add the following to your config.yaml:\n")
    print("  hitl:")
    print(f"    db_host: \"{params['host']}\"")
    print(f"    db_port: {params['port']}")
    print(f"    db_name: \"{params['database']}\"")
    print(f"    db_user: \"{params['user']}\"")
    print(f"    db_password: \"${{ORCA_PG_PASSWORD:-}}\"  # use env var")
    print(f"    db_schema: \"{SCHEMA_NAME}\"")
    print()


# ── SQLite Migration ──────────────────────────────────────────────────────

def migrate_from_sqlite(sqlite_path: str, params: dict):
    """Import all rows from an existing SQLite feedback database into PostgreSQL."""
    import sqlite3

    if not os.path.isfile(sqlite_path):
        print(f"  SQLite file not found: {sqlite_path}")
        return 0

    print(f"  Migrating from SQLite: {sqlite_path}")

    sq_conn = sqlite3.connect(sqlite_path)
    sq_cur = sq_conn.cursor()
    sq_cur.execute("""
        SELECT project, file_path, rule_id, violation_text,
               decision, constraints, reviewer, timestamp, confidence
        FROM compliance_decisions
        ORDER BY id
    """)
    rows = sq_cur.fetchall()
    sq_conn.close()

    if not rows:
        print("  No rows found in SQLite database.")
        return 0

    import psycopg2
    pg_conn = _connect(params)
    pg_cur = pg_conn.cursor()

    insert_sql = f"""
        INSERT INTO {SCHEMA_NAME}.compliance_decisions
            (project, file_path, rule_id, violation_text,
             decision, constraints, reviewer, timestamp, confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    migrated = 0
    for row in rows:
        try:
            pg_cur.execute(insert_sql, row)
            migrated += 1
        except Exception as e:
            logger.warning(f"Skipped row: {e}")

    pg_cur.close()
    pg_conn.close()

    print(f"  Migrated {migrated}/{len(rows)} decisions to PostgreSQL.")
    return migrated


# ── CLI ───────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ORCA — PostgreSQL Database Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--host",     default="", help="PostgreSQL host (env: ORCA_PG_HOST, default: localhost)")
    p.add_argument("--port",     default="", help="PostgreSQL port (env: ORCA_PG_PORT, default: 5432)")
    p.add_argument("--user",     default="", help="PostgreSQL user (env: ORCA_PG_USER, default: orca)")
    p.add_argument("--password", default="", help="PostgreSQL password (env: ORCA_PG_PASSWORD)")
    p.add_argument("--database", default="", help="Database name (env: ORCA_PG_DATABASE, default: orca_feedback)")

    p.add_argument("--tables-only", action="store_true",
                   help="Skip database creation; only create schema/tables/indexes")
    p.add_argument("--reset", action="store_true",
                   help="Drop and recreate schema (DESTRUCTIVE)")
    p.add_argument("--migrate-from", metavar="SQLITE_PATH",
                   help="Migrate data from an existing SQLite feedback DB")
    p.add_argument("--skip-verify", action="store_true",
                   help="Skip the post-setup verification step")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    check_psycopg2()
    params = get_connection_params(args)

    print("=" * 60)
    print("  ORCA PostgreSQL Setup")
    print("=" * 60)
    print(f"  Host:     {params['host']}:{params['port']}")
    print(f"  Database: {params['database']}")
    print(f"  User:     {params['user']}")
    print(f"  Schema:   {SCHEMA_NAME}")
    print()

    # Step 0: Verify PostgreSQL is reachable
    print("[0/4] Checking PostgreSQL connectivity...")
    if not check_pg_server(params):
        sys.exit(1)
    print("  PostgreSQL is reachable.")
    print()

    # Step 1: Create database (unless --tables-only)
    if not args.tables_only:
        print("[1/4] Creating database...")
        create_database(params)
    else:
        print("[1/4] Skipped database creation (--tables-only)")

    # Step 2: Create schema, tables, indexes
    if args.reset:
        print("[2/4] Resetting schema (--reset)...")
        reset_database(params)
    else:
        print("[2/4] Creating schema and tables...")
        create_schema_and_tables(params)

    # Step 3: Verify
    if not args.skip_verify:
        print("[3/4] Verifying setup...")
        ok = verify_setup(params)
        if not ok:
            print("\nSetup verification failed. Check connection and permissions.")
            sys.exit(1)
    else:
        print("[3/4] Skipped verification (--skip-verify)")

    # Step 4: Migrate from SQLite (optional)
    if args.migrate_from:
        print(f"[4/4] Migrating from SQLite ({args.migrate_from})...")
        migrate_from_sqlite(args.migrate_from, params)
    else:
        print("[4/4] No SQLite migration requested")

    print()
    print("Setup complete!")
    print_connection_info(params)


if __name__ == "__main__":
    main()
