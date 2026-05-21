import os


DATABASE_URL_ENV = "DATABASE_URL"
ORDER_SCHEMA_MIGRATION_ID = "202605210002_create_order_sales_tables"
ORDER_SCHEMA_TABLES = [
    "orders",
    "order_lines",
    "order_intakes",
    "order_intake_items",
    "order_documents",
    "order_status_logs",
    "sales_pricing",
]


def check_database_health():
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": "DATABASE_URL is not configured.",
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select now() at time zone 'utc', current_database()")
                database_time_utc, database_name = cursor.fetchone()

        return {
            "success": True,
            "configured": True,
            "status": "ok",
            "database": database_name,
            "database_time_utc": database_time_utc.isoformat(),
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "connection_failed",
            "message": "Database health check failed.",
            "error_type": exc.__class__.__name__,
        }, 503


def check_database_foundation():
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": "DATABASE_URL is not configured.",
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
        }, 500

    migration_id = "202605210001_foundation_migration_log"

    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select migration_id, description, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (migration_id,),
                )
                row = cursor.fetchone()

        if not row:
            return {
                "success": False,
                "configured": True,
                "status": "foundation_missing",
                "migration_id": migration_id,
                "message": "Foundation migration has not been applied.",
            }, 503

        found_migration_id, description, applied_at = row
        return {
            "success": True,
            "configured": True,
            "status": "ok",
            "migration_id": found_migration_id,
            "description": description,
            "applied_at": applied_at.isoformat(),
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "foundation_check_failed",
            "message": "Database foundation check failed.",
            "error_type": exc.__class__.__name__,
        }, 503


def check_order_schema():
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": "DATABASE_URL is not configured.",
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public'
                    and table_name = any(%s)
                    """,
                    (ORDER_SCHEMA_TABLES,),
                )
                found_tables = sorted(row[0] for row in cursor.fetchall())

                cursor.execute(
                    """
                    select migration_id, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (ORDER_SCHEMA_MIGRATION_ID,),
                )
                migration_row = cursor.fetchone()

        expected_tables = sorted(ORDER_SCHEMA_TABLES)
        missing_tables = [table for table in expected_tables if table not in found_tables]

        if missing_tables or not migration_row:
            return {
                "success": False,
                "configured": True,
                "status": "order_schema_missing",
                "migration_id": ORDER_SCHEMA_MIGRATION_ID,
                "migration_applied": bool(migration_row),
                "expected_tables": expected_tables,
                "found_tables": found_tables,
                "missing_tables": missing_tables,
            }, 503

        return {
            "success": True,
            "configured": True,
            "status": "ok",
            "migration_id": migration_row[0],
            "applied_at": migration_row[1].isoformat(),
            "expected_tables": expected_tables,
            "found_tables": found_tables,
            "missing_tables": [],
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "order_schema_check_failed",
            "message": "Order schema check failed.",
            "error_type": exc.__class__.__name__,
        }, 503
