#!/usr/bin/env python3
"""ORCA — Full PostgreSQL Bootstrap (no Docker required).

This script handles the complete PostgreSQL lifecycle on a local machine:

  1. Detects the operating system (macOS / Linux)
  2. Installs PostgreSQL via the native package manager if missing
  3. Starts the PostgreSQL service if not already running
  4. Creates the ORCA database user (if it doesn't exist)
  5. Creates the ORCA database (if it doesn't exist)
  6. Creates the 'orca' schema, tables, indexes, and constraints
  7. Runs a quick smoke-test to verify everything works
  8. Optionally migrates data from a legacy SQLite database

Usage:
    # One-command bootstrap (auto-detects everything):
    python bootstrap_db.py

    # Custom user/database names:
    python bootstrap_db.py --user myuser --password secret --database mydb

    # Skip PostgreSQL install/start (assume it's already running):
    python bootstrap_db.py --skip-install

    # Reset schema (drop + recreate — DESTRUCTIVE):
    python bootstrap_db.py --reset

    # Migrate from legacy SQLite:
    python bootstrap_db.py --migrate-from ./orca_feedback.db
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import logging

logger = logging.getLogger("orca.bootstrap")

# Re-use SQL definitions from setup_db so there's a single source of truth
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from setup_db import (
    SCHEMA_NAME,
    CREATE_SCHEMA,
    CREATE_TABLE,
    CREATE_INDEXES,
    ADD_DECISION_CHECK,
    DROP_TABLE,
    DROP_SCHEMA,
    verify_setup,
    migrate_from_sqlite,
    print_connection_info,
)

# ═════════════════════════════════════════════════════════════════════════
#  Platform Detection
# ═════════════════════════════════════════════════════════════════════════

def detect_platform() -> str:
    """Return 'macos', 'debian', 'rhel', or 'unknown'."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system != "linux":
        return "unknown"
    # Distinguish distro family
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
        if any(d in content for d in ("ubuntu", "debian", "pop!_os", "mint")):
            return "debian"
        if any(d in content for d in ("rhel", "fedora", "centos", "rocky", "alma")):
            return "rhel"
    except FileNotFoundError:
        pass
    return "unknown"


def _run(cmd: list[str], check: bool = True, capture: bool = False, **kw):
    """Thin wrapper around subprocess.run with nice defaults."""
    if capture:
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
        kw.setdefault("text", True)
    return subprocess.run(cmd, check=check, **kw)


def _has_command(name: str) -> bool:
    return shutil.which(name) is not None


# ═════════════════════════════════════════════════════════════════════════
#  Step 1 — Install PostgreSQL
# ═════════════════════════════════════════════════════════════════════════

def install_postgresql(plat: str):
    """Install PostgreSQL using the platform's package manager."""

    if _has_command("psql"):
        ver = _run(["psql", "--version"], capture=True, check=False)
        print(f"  PostgreSQL already installed: {ver.stdout.strip()}")
        return

    print("  PostgreSQL not found — installing...")

    if plat == "macos":
        if not _has_command("brew"):
            print("\n  ERROR: Homebrew is required on macOS.")
            print("  Install it from https://brew.sh and re-run this script.")
            sys.exit(1)
        _run(["brew", "install", "postgresql@16"])
        # Ensure the keg-only binaries are on PATH for this session
        pg_bin = subprocess.run(
            ["brew", "--prefix", "postgresql@16"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() + "/bin"
        if pg_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = pg_bin + ":" + os.environ.get("PATH", "")
        print(f"  Installed via Homebrew. Binaries at {pg_bin}")

    elif plat == "debian":
        _run(["sudo", "apt-get", "update", "-qq"])
        _run(["sudo", "apt-get", "install", "-y", "-qq", "postgresql", "postgresql-client"])
        print("  Installed via apt.")

    elif plat == "rhel":
        _run(["sudo", "dnf", "install", "-y", "postgresql-server", "postgresql"])
        # initdb if data directory is empty
        result = _run(["sudo", "postgresql-setup", "--initdb"], check=False, capture=True)
        if result.returncode == 0:
            print("  Initialized PostgreSQL data directory.")
        print("  Installed via dnf.")

    else:
        print("\n  ERROR: Unsupported platform. Install PostgreSQL manually:")
        print("    https://www.postgresql.org/download/")
        sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════
#  Step 2 — Start PostgreSQL Service
# ═════════════════════════════════════════════════════════════════════════

def _pg_is_running(host: str = "localhost", port: int = 5432) -> bool:
    """Quick check: can we reach PostgreSQL on the given host:port?"""
    if _has_command("pg_isready"):
        r = _run(["pg_isready", "-h", host, "-p", str(port)],
                 check=False, capture=True)
        return r.returncode == 0
    # Fallback: try a TCP connection
    import socket
    try:
        s = socket.create_connection((host, port), timeout=3)
        s.close()
        return True
    except OSError:
        return False


def start_postgresql(plat: str, port: int = 5432):
    """Ensure the PostgreSQL service is running."""

    if _pg_is_running(port=port):
        print("  PostgreSQL is already running.")
        return

    print("  Starting PostgreSQL service...")

    if plat == "macos":
        _run(["brew", "services", "start", "postgresql@16"], check=False)

    elif plat == "debian":
        _run(["sudo", "systemctl", "start", "postgresql"], check=False)

    elif plat == "rhel":
        _run(["sudo", "systemctl", "start", "postgresql"], check=False)

    else:
        print("  WARNING: Cannot auto-start PostgreSQL on this platform.")
        print("  Please start it manually and re-run this script.")
        sys.exit(1)

    # Wait up to 15 seconds for the server to become ready
    for i in range(15):
        time.sleep(1)
        if _pg_is_running(port=port):
            print("  PostgreSQL started successfully.")
            return

    print("  ERROR: PostgreSQL did not start within 15 seconds.")
    print("  Check logs with: journalctl -u postgresql (Linux)")
    print("                   brew services info postgresql@16 (macOS)")
    sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════
#  Step 3 — Create User
# ═════════════════════════════════════════════════════════════════════════

def _pg_superuser() -> str:
    """Return the OS-level superuser that can run createuser/createdb.

    On macOS + Homebrew, the current user owns the cluster.
    On Linux, the 'postgres' system user owns the cluster.
    """
    if platform.system().lower() == "darwin":
        return os.environ.get("USER", "")
    return "postgres"


def _run_as_pg(cmd: list[str], check: bool = True, capture: bool = False):
    """Run a command as the PostgreSQL superuser."""
    su = _pg_superuser()
    current = os.environ.get("USER", "")
    if su and su != current and su == "postgres":
        full_cmd = ["sudo", "-u", su] + cmd
    else:
        full_cmd = cmd
    return _run(full_cmd, check=check, capture=capture)


def create_user(user: str, password: str):
    """Create the PostgreSQL role if it doesn't exist."""
    # Check if role already exists
    r = _run_as_pg(
        ["psql", "-tAc", f"SELECT 1 FROM pg_roles WHERE rolname='{user}'", "postgres"],
        check=False, capture=True,
    )
    if r.stdout.strip() == "1":
        print(f"  Role '{user}' already exists.")
        return

    print(f"  Creating role '{user}'...")
    if password:
        _run_as_pg(
            ["psql", "-c", f"CREATE ROLE \"{user}\" WITH LOGIN PASSWORD '{password}' CREATEDB;", "postgres"],
        )
    else:
        _run_as_pg(
            ["psql", "-c", f"CREATE ROLE \"{user}\" WITH LOGIN CREATEDB;", "postgres"],
        )
    print(f"  Role '{user}' created.")


# ═════════════════════════════════════════════════════════════════════════
#  Step 4 — Create Database
# ═════════════════════════════════════════════════════════════════════════

def create_database(user: str, database: str):
    """Create the target database if it doesn't exist."""
    r = _run_as_pg(
        ["psql", "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{database}'", "postgres"],
        check=False, capture=True,
    )
    if r.stdout.strip() == "1":
        print(f"  Database '{database}' already exists.")
        return

    print(f"  Creating database '{database}' owned by '{user}'...")
    _run_as_pg(["createdb", "-O", user, database])
    print(f"  Database '{database}' created.")


# ═════════════════════════════════════════════════════════════════════════
#  Step 5 — Create Schema, Tables, Indexes
# ═════════════════════════════════════════════════════════════════════════

def _pg_connect(params: dict):
    """Connect to the target database via psycopg2."""
    import psycopg2
    conn = psycopg2.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database=params["database"],
    )
    conn.autocommit = True
    return conn


def create_schema_and_tables(params: dict):
    """Create schema, table, indexes, and constraints."""
    conn = _pg_connect(params)
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


def reset_schema(params: dict):
    """Drop and recreate schema (DESTRUCTIVE)."""
    conn = _pg_connect(params)
    cur = conn.cursor()
    cur.execute(DROP_TABLE)
    cur.execute(DROP_SCHEMA)
    print("  Dropped existing schema and tables.")
    cur.close()
    conn.close()
    create_schema_and_tables(params)


# ═════════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════════

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ORCA — Full PostgreSQL Bootstrap (no Docker)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--host",     default="localhost",
                   help="PostgreSQL host (default: localhost)")
    p.add_argument("--port",     type=int, default=5432,
                   help="PostgreSQL port (default: 5432)")
    p.add_argument("--user",     default=_env("ORCA_PG_USER", "orca"),
                   help="DB user to create/use (default: orca)")
    p.add_argument("--password", default=_env("ORCA_PG_PASSWORD", ""),
                   help="Password for the DB user (default: none)")
    p.add_argument("--database", default=_env("ORCA_PG_DATABASE", "orca_feedback"),
                   help="Database name (default: orca_feedback)")

    p.add_argument("--skip-install", action="store_true",
                   help="Skip PostgreSQL install and service start")
    p.add_argument("--reset", action="store_true",
                   help="Drop and recreate the orca schema (DESTRUCTIVE)")
    p.add_argument("--migrate-from", metavar="SQLITE_PATH",
                   help="Migrate data from a legacy SQLite feedback DB")
    p.add_argument("--skip-verify", action="store_true",
                   help="Skip the post-setup smoke test")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Verbose output")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    plat = detect_platform()

    params = {
        "host":     args.host,
        "port":     args.port,
        "user":     args.user,
        "password": args.password,
        "database": args.database,
    }

    print()
    print("=" * 60)
    print("  ORCA — PostgreSQL Bootstrap")
    print("=" * 60)
    print(f"  Platform: {plat}")
    print(f"  Host:     {params['host']}:{params['port']}")
    print(f"  User:     {params['user']}")
    print(f"  Database: {params['database']}")
    print(f"  Schema:   {SCHEMA_NAME}")
    print()

    # ── Step 1: Install PostgreSQL ────────────────────────────────────
    if not args.skip_install:
        print("[1/6] Installing PostgreSQL (if needed)...")
        install_postgresql(plat)
    else:
        print("[1/6] Skipped PostgreSQL install (--skip-install)")
    print()

    # ── Step 2: Start service ─────────────────────────────────────────
    if not args.skip_install:
        print("[2/6] Starting PostgreSQL service...")
        start_postgresql(plat, port=params["port"])
    else:
        print("[2/6] Skipped service start (--skip-install)")

        if not _pg_is_running(port=params["port"]):
            print(f"\n  ERROR: PostgreSQL is not running on port {params['port']}.")
            print("  Start it manually or re-run without --skip-install.\n")
            sys.exit(1)
        print("  PostgreSQL is running.")
    print()

    # ── Step 3: Create user ───────────────────────────────────────────
    print(f"[3/6] Creating database user '{params['user']}'...")
    try:
        create_user(params["user"], params["password"])
    except Exception as e:
        print(f"  WARNING: Could not create user: {e}")
        print(f"  Continuing — the user may already exist or you may need")
        print(f"  to create it manually: createuser -s {params['user']}")
    print()

    # ── Step 4: Create database ───────────────────────────────────────
    print(f"[4/6] Creating database '{params['database']}'...")
    try:
        create_database(params["user"], params["database"])
    except Exception as e:
        print(f"  WARNING: Could not create database: {e}")
        print(f"  Continuing — the database may already exist or you may")
        print(f"  need to create it manually: createdb -O {params['user']} {params['database']}")
    print()

    # ── Step 5: Create schema + tables ────────────────────────────────
    # First make sure psycopg2 is available
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("  ERROR: psycopg2 is not installed.")
        print("  Run:  pip install psycopg2-binary")
        sys.exit(1)

    if args.reset:
        print("[5/6] Resetting schema (--reset)...")
        reset_schema(params)
    else:
        print("[5/6] Creating schema and tables...")
        create_schema_and_tables(params)
    print()

    # ── Step 6: Verify ────────────────────────────────────────────────
    if not args.skip_verify:
        print("[6/6] Verifying setup...")
        # verify_setup expects params with 'database' key — same shape we have
        ok = verify_setup(params)
        if not ok:
            print("\n  Verification failed. Check connection and permissions.")
            sys.exit(1)
    else:
        print("[6/6] Skipped verification (--skip-verify)")
    print()

    # ── Optional: SQLite migration ────────────────────────────────────
    if args.migrate_from:
        print(f"[+] Migrating from SQLite ({args.migrate_from})...")
        migrate_from_sqlite(args.migrate_from, params)
        print()

    # ── Done ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("  Bootstrap complete!")
    print("=" * 60)
    print_connection_info(params)
    print("  Next steps:")
    print("    1. Update .env with your ORCA_PG_* values (if needed)")
    print("    2. Run:  python main.py audit --codebase-path ./src")
    print()


if __name__ == "__main__":
    main()
