import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.order_sales_shadow_import import IMPORT_BATCH_ID, TABLE_INSERT_ORDER, load_local_env
from services.database_service import DATABASE_URL_ENV


def verify_shadow_import(database_url, import_batch_id=IMPORT_BATCH_ID, connect_factory=None):
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
        }, 2

    if connect_factory is None:
        try:
            import psycopg
        except ImportError:
            return {
                "success": False,
                "configured": True,
                "status": "dependency_missing",
                "message": "Python database dependency is not installed.",
            }, 2
        connect_factory = psycopg.connect

    try:
        with connect_factory(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                counts = {}
                samples = {}
                for table_name in TABLE_INSERT_ORDER:
                    cursor.execute(
                        f"select count(*) from public.{table_name} where import_batch_id = %s",
                        (import_batch_id,),
                    )
                    counts[table_name] = cursor.fetchone()[0]

                    id_column = {
                        "sales_pricing": "pricing_id",
                        "orders": "order_id",
                        "order_lines": "order_line_id",
                        "order_intakes": "intake_id",
                        "order_intake_items": "intake_item_id",
                        "order_documents": "document_id",
                        "order_status_logs": "status_log_id",
                    }[table_name]
                    cursor.execute(
                        f"""
                        select {id_column}
                        from public.{table_name}
                        where import_batch_id = %s
                        order by {id_column}
                        limit 3
                        """,
                        (import_batch_id,),
                    )
                    samples[table_name] = [row[0] for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "verification_failed",
            "message": "Shadow import verification failed.",
            "error_type": exc.__class__.__name__,
        }, 1

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "import_batch_id": import_batch_id,
        "counts": counts,
        "sample_ids": samples,
    }, 0


def main():
    load_local_env()
    report, exit_code = verify_shadow_import(os.getenv(DATABASE_URL_ENV, "").strip())
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
