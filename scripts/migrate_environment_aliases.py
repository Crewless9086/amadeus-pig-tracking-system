"""Stage canonical CHARLIE/CORE dotenv aliases without exposing values."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.charlie.environment import ALIASES, EnvironmentConflictError, env_value


MANAGED_HEADER = "# Phase 1 canonical CHARLIE/CORE aliases (legacy keys retained)"
DYNAMIC_CORE_PREFIXES = (
    "CHARLIE_AGENT_MODEL_",
    "CHARLIE_AGENT_PROVIDER_",
    "CHARLIE_MODEL_",
    "CHARLIE_PROVIDER_",
)


def parse_dotenv(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value
    return values


def migration_plan(values, *, excluded=()):
    excluded = set(excluded)
    additions = {}
    equal = []
    conflicts = []
    aliases = dict(ALIASES)
    for legacy in values:
        if legacy.startswith(DYNAMIC_CORE_PREFIXES):
            aliases.setdefault("CORE_" + legacy[len("CHARLIE_"):], (legacy,))
    for canonical, legacy_names in aliases.items():
        if canonical in excluded:
            continue
        present_legacy = [name for name in legacy_names if name in values]
        if not present_legacy and canonical not in values:
            continue
        try:
            resolved = env_value(canonical, environ=values, aliases=legacy_names)
        except EnvironmentConflictError:
            conflicts.append(canonical)
            continue
        if canonical in values:
            equal.append(canonical)
        else:
            additions[canonical] = resolved
    return additions, equal, conflicts


def migrate(path, *, apply=False, backup_dir=None, excluded=()):
    original = path.read_text(encoding="utf-8")
    values = parse_dotenv(original)
    additions, equal, conflicts = migration_plan(values, excluded=excluded)
    result = {
        "path": str(path),
        "additions": sorted(additions),
        "already_equal": sorted(equal),
        "conflicts": sorted(conflicts),
        "applied": False,
    }
    if conflicts or not apply or not additions:
        return result
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, backup)
    suffix = "\n" if original.endswith("\n") else "\n\n"
    block = [MANAGED_HEADER, *(f"{key}={additions[key]}" for key in sorted(additions))]
    path.write_text(original + suffix + "\n".join(block) + "\n", encoding="utf-8")
    result["applied"] = True
    result["backup_created"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args(argv)
    backup_dir = args.backup_dir or args.path.parent / ".charlie_runner" / "environment_backups"
    result = migrate(args.path, apply=args.apply, backup_dir=backup_dir, excluded=args.exclude)
    for label in ("additions", "already_equal", "conflicts"):
        print(f"{label}={','.join(result[label]) or '-'}")
    print(f"applied={str(result['applied']).lower()}")
    if result["conflicts"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
