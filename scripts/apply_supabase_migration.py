import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.database_service import DATABASE_URL_ENV


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply one reviewed Supabase SQL migration.")
    parser.add_argument("migration", help="Path under supabase/migrations")
    args = parser.parse_args()

    migration_path = (REPO_ROOT / args.migration).resolve()
    migrations_dir = (REPO_ROOT / "supabase" / "migrations").resolve()

    if migrations_dir not in migration_path.parents:
        raise SystemExit("Refusing to run SQL outside supabase/migrations.")
    if migration_path.suffix.lower() != ".sql":
        raise SystemExit("Migration file must be a .sql file.")
    if not migration_path.exists():
        raise SystemExit(f"Migration file not found: {migration_path}")

    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise SystemExit(f"{DATABASE_URL_ENV} is not configured.")

    sql = migration_path.read_text(encoding="utf-8")
    import psycopg

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)

    print(f"Applied migration: {migration_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
