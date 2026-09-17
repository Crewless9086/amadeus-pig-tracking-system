import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.database_service import DATABASE_URL_ENV


SUPERSESSIONS_PATH = REPO_ROOT / "supabase" / "migrations" / "supersessions.json"
SUPPORTED_SUPERSESSIONS_SCHEMA_VERSION = 1
SUPERSEDED_ENTRY_STATUSES = frozenset({"superseded_unapplied"})


def canonical_migration_key(value) -> str:
    key = str(value or "").strip()
    if not key:
        raise SystemExit("Invalid empty migration supersession key.")
    return key.casefold()


def load_supersessions(registry_path: Path | None = None):
    registry_path = registry_path or SUPERSESSIONS_PATH
    try:
        raw = registry_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit("Migration supersessions registry is missing or unreadable.") from exc
    if not raw.strip():
        raise SystemExit("Migration supersessions registry is empty.")
    try:
        registry = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SystemExit("Migration supersessions registry is malformed.") from exc
    if not isinstance(registry, dict):
        raise SystemExit("Migration supersessions registry must be an object.")
    if (
        type(registry.get("schema_version")) is not int
        or registry["schema_version"] != SUPPORTED_SUPERSESSIONS_SCHEMA_VERSION
    ):
        raise SystemExit("Unsupported migration supersessions schema_version.")
    if "superseded_migrations" not in registry:
        raise SystemExit("Migration supersessions registry is missing superseded_migrations.")
    if set(registry) != {"schema_version", "superseded_migrations"}:
        raise SystemExit("Migration supersessions registry has invalid fields.")
    migrations = registry["superseded_migrations"]
    if not isinstance(migrations, dict) or not migrations:
        raise SystemExit("superseded_migrations must be a non-empty object.")

    canonical = {}
    for key, entry in migrations.items():
        if (
            not isinstance(key, str)
            or key != key.strip()
            or "/" in key
            or "\\" in key
            or Path(key).suffix
        ):
            raise SystemExit("Migration supersession keys must be strings.")
        canonical_key = canonical_migration_key(key)
        if canonical_key in canonical:
            raise SystemExit("Canonical migration supersession key collision.")
        if not isinstance(entry, dict):
            raise SystemExit("Migration supersession entries must be objects.")
        if set(entry) != {"status", "reason"}:
            raise SystemExit("Migration supersession entries have invalid fields.")
        status = entry.get("status")
        reason = entry.get("reason")
        if not isinstance(status, str) or status not in SUPERSEDED_ENTRY_STATUSES:
            raise SystemExit("Invalid migration supersession entry status.")
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit("Invalid migration supersession entry reason.")
        canonical[canonical_key] = {"status": status, "reason": reason.strip()}
    return canonical


def supersession_for(migration_path: Path, registry_path: Path | None = None):
    migrations = load_supersessions(registry_path)
    return migrations.get(canonical_migration_key(migration_path.stem))


def resolve_migration_path(requested: str) -> Path:
    migrations_dir = (REPO_ROOT / "supabase" / "migrations").resolve()
    raw_path = Path(requested)
    if (
        raw_path.is_absolute()
        or len(raw_path.parts) != 3
        or tuple(part.casefold() for part in raw_path.parts[:2])
        != ("supabase", "migrations")
        or raw_path.name != raw_path.parts[-1]
    ):
        raise SystemExit("Migration path must be canonical under supabase/migrations.")
    requested_path = (REPO_ROOT / raw_path).resolve()
    if requested_path.parent != migrations_dir:
        raise SystemExit("Refusing to run SQL outside supabase/migrations.")
    if requested_path.suffix.casefold() != ".sql":
        raise SystemExit("Migration file must be a .sql file.")
    matches = [
        candidate
        for candidate in migrations_dir.iterdir()
        if candidate.is_file()
        and candidate.name.casefold() == requested_path.name.casefold()
    ]
    if len(matches) != 1:
        raise SystemExit("Migration file is missing or has a canonical-name collision.")
    return matches[0].resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply one reviewed Supabase SQL migration.")
    parser.add_argument("migration", help="Path under supabase/migrations")
    args = parser.parse_args()

    migration_path = resolve_migration_path(args.migration)

    supersession = supersession_for(migration_path)
    if supersession is not None:
        status = str(supersession.get("status") or "superseded")
        reason = str(supersession.get("reason") or "No replacement is currently authorized.")
        raise SystemExit(
            f"Refusing superseded migration {migration_path.stem} "
            f"({status}): {reason}"
        )

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
