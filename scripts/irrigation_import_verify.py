import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.irrigation_import_dry_run import APPLY_IMPORT_BATCH_ID, load_local_env
from services.database_service import DATABASE_URL_ENV


TABLES = [
    "irrigation_zones",
    "irrigation_daily_plans",
    "irrigation_plan_items",
    "irrigation_state_snapshots",
    "irrigation_events",
]


def verify_irrigation_import(database_url, import_batch_id=APPLY_IMPORT_BATCH_ID, connect_factory=None):
    if not database_url:
        return {
            "success": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
        }, 2

    if connect_factory is None:
        try:
            import psycopg
        except ImportError:
            return {
                "success": False,
                "status": "dependency_missing",
                "message": "Python database dependency is not installed.",
            }, 2
        connect_factory = psycopg.connect

    try:
        with connect_factory(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                table_counts = {}
                import_batch_counts = {}
                for table_name in TABLES:
                    cursor.execute(f"select count(*) from public.{table_name}")
                    table_counts[table_name] = cursor.fetchone()[0]
                    cursor.execute(
                        f"select count(*) from public.{table_name} where import_batch_id = %s",
                        (import_batch_id,),
                    )
                    import_batch_counts[table_name] = cursor.fetchone()[0]

                cursor.execute(
                    """
                    select state_snapshot_id, current_status, current_zone_id, next_zone_id, import_batch_id
                    from public.irrigation_state_snapshots
                    order by state_snapshot_id
                    """
                )
                state_rows = [
                    {
                        "state_snapshot_id": row[0],
                        "current_status": row[1],
                        "current_zone_id": row[2],
                        "next_zone_id": row[3],
                        "import_batch_id": row[4],
                    }
                    for row in cursor.fetchall()
                ]
    except Exception as exc:
        return {
            "success": False,
            "status": "verification_failed",
            "message": "Irrigation import verification failed.",
            "error_type": exc.__class__.__name__,
            "error_message": str(exc)[:500],
        }, 1

    return {
        "success": True,
        "status": "ok",
        "import_batch_id": import_batch_id,
        "table_counts": table_counts,
        "import_batch_counts": import_batch_counts,
        "state_rows": state_rows,
        "state_strategy_verified": len(state_rows) == 1 and state_rows[0]["state_snapshot_id"] == "IRRSTATE-MAIN",
    }, 0


def main():
    parser = argparse.ArgumentParser(description="Verify irrigation Supabase import counts.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    load_local_env()

    report, exit_code = verify_irrigation_import(os.getenv(DATABASE_URL_ENV, "").strip())
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
