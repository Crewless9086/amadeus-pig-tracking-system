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
SALES_TRANSACTION_SCHEMA_MIGRATION_ID = "202605210003_create_sales_transaction_tables"
SALES_TRANSACTION_SCHEMA_TABLES = [
    "sales_transactions",
    "sales_transaction_items",
]
SALES_PAYMENT_DATE_MIGRATION_ID = "202605210004_add_sales_transaction_payment_date"
TELEMETRY_POWER_SCHEMA_MIGRATION_ID = "202605210005_create_telemetry_power_tables"
TELEMETRY_POWER_SCHEMA_TABLES = [
    "telemetry_sources",
    "power_readings_5min",
    "power_latest_state",
    "telemetry_alerts",
]
TELEMETRY_WEATHER_SCHEMA_MIGRATION_ID = "202605220001_create_telemetry_weather_tables"
TELEMETRY_WEATHER_SCHEMA_TABLES = [
    "weather_readings",
    "weather_latest_state",
    "weather_forecast_snapshots",
]
IRRIGATION_SCHEMA_MIGRATION_ID = "202605230001_create_irrigation_tables"
IRRIGATION_SCHEMA_TABLES = [
    "irrigation_zones",
    "irrigation_daily_plans",
    "irrigation_plan_items",
    "irrigation_state_snapshots",
    "irrigation_events",
    "irrigation_auxiliary_devices",
    "irrigation_auxiliary_tasks",
    "irrigation_sensor_states",
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


def check_sales_transaction_schema():
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
                    (SALES_TRANSACTION_SCHEMA_TABLES,),
                )
                found_tables = sorted(row[0] for row in cursor.fetchall())

                cursor.execute(
                    """
                    select migration_id, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (SALES_TRANSACTION_SCHEMA_MIGRATION_ID,),
                )
                migration_row = cursor.fetchone()

        expected_tables = sorted(SALES_TRANSACTION_SCHEMA_TABLES)
        missing_tables = [table for table in expected_tables if table not in found_tables]

        if missing_tables or not migration_row:
            return {
                "success": False,
                "configured": True,
                "status": "sales_transaction_schema_missing",
                "migration_id": SALES_TRANSACTION_SCHEMA_MIGRATION_ID,
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
            "status": "sales_transaction_schema_check_failed",
            "message": "Sales transaction schema check failed.",
            "error_type": exc.__class__.__name__,
        }, 503


def check_sales_transaction_payment_date_schema():
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
                    select column_name
                    from information_schema.columns
                    where table_schema = 'public'
                    and table_name = 'sales_transactions'
                    and column_name = 'payment_date'
                    """
                )
                column_row = cursor.fetchone()

                cursor.execute(
                    """
                    select migration_id, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (SALES_PAYMENT_DATE_MIGRATION_ID,),
                )
                migration_row = cursor.fetchone()

        if not column_row or not migration_row:
            return {
                "success": False,
                "configured": True,
                "status": "sales_payment_date_schema_missing",
                "migration_id": SALES_PAYMENT_DATE_MIGRATION_ID,
                "migration_applied": bool(migration_row),
                "payment_date_column_found": bool(column_row),
            }, 503

        return {
            "success": True,
            "configured": True,
            "status": "ok",
            "migration_id": migration_row[0],
            "applied_at": migration_row[1].isoformat(),
            "payment_date_column_found": True,
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_payment_date_schema_check_failed",
            "message": "Sales payment date schema check failed.",
            "error_type": exc.__class__.__name__,
        }, 503


def check_telemetry_power_schema():
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
                    (TELEMETRY_POWER_SCHEMA_TABLES,),
                )
                found_tables = sorted(row[0] for row in cursor.fetchall())

                cursor.execute(
                    """
                    select migration_id, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (TELEMETRY_POWER_SCHEMA_MIGRATION_ID,),
                )
                migration_row = cursor.fetchone()

                cursor.execute(
                    """
                    select source_id, source_type, provider, stale_after_minutes
                    from public.telemetry_sources
                    where source_id = 'sunsynk-main-inverter'
                    """
                )
                source_row = cursor.fetchone()

        expected_tables = sorted(TELEMETRY_POWER_SCHEMA_TABLES)
        missing_tables = [table for table in expected_tables if table not in found_tables]

        if missing_tables or not migration_row or not source_row:
            return {
                "success": False,
                "configured": True,
                "status": "telemetry_power_schema_missing",
                "migration_id": TELEMETRY_POWER_SCHEMA_MIGRATION_ID,
                "migration_applied": bool(migration_row),
                "expected_tables": expected_tables,
                "found_tables": found_tables,
                "missing_tables": missing_tables,
                "sunsynk_source_found": bool(source_row),
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
            "sunsynk_source": {
                "source_id": source_row[0],
                "source_type": source_row[1],
                "provider": source_row[2],
                "stale_after_minutes": source_row[3],
            },
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "telemetry_power_schema_check_failed",
            "message": "Telemetry power schema check failed.",
            "error_type": exc.__class__.__name__,
        }, 503


def check_telemetry_weather_schema():
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
                    (TELEMETRY_WEATHER_SCHEMA_TABLES,),
                )
                found_tables = sorted(row[0] for row in cursor.fetchall())

                cursor.execute(
                    """
                    select migration_id, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (TELEMETRY_WEATHER_SCHEMA_MIGRATION_ID,),
                )
                migration_row = cursor.fetchone()

                cursor.execute(
                    """
                    select source_id, source_type, provider, stale_after_minutes
                    from public.telemetry_sources
                    where source_id in ('weather-station-main', 'open-meteo-forecast-main')
                    order by source_id
                    """
                )
                source_rows = cursor.fetchall()

        expected_tables = sorted(TELEMETRY_WEATHER_SCHEMA_TABLES)
        missing_tables = [table for table in expected_tables if table not in found_tables]
        source_by_id = {row[0]: row for row in source_rows}

        if (
            missing_tables
            or not migration_row
            or "weather-station-main" not in source_by_id
            or "open-meteo-forecast-main" not in source_by_id
        ):
            return {
                "success": False,
                "configured": True,
                "status": "telemetry_weather_schema_missing",
                "migration_id": TELEMETRY_WEATHER_SCHEMA_MIGRATION_ID,
                "migration_applied": bool(migration_row),
                "expected_tables": expected_tables,
                "found_tables": found_tables,
                "missing_tables": missing_tables,
                "weather_source_found": "weather-station-main" in source_by_id,
                "forecast_source_found": "open-meteo-forecast-main" in source_by_id,
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
            "sources": {
                row[0]: {
                    "source_id": row[0],
                    "source_type": row[1],
                    "provider": row[2],
                    "stale_after_minutes": row[3],
                }
                for row in source_rows
            },
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "telemetry_weather_schema_check_failed",
            "message": "Telemetry weather schema check failed.",
            "error_type": exc.__class__.__name__,
        }, 503


def check_irrigation_schema():
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
                    (IRRIGATION_SCHEMA_TABLES,),
                )
                found_tables = sorted(row[0] for row in cursor.fetchall())

                cursor.execute(
                    """
                    select migration_id, applied_at
                    from app_private.migration_log
                    where migration_id = %s
                    """,
                    (IRRIGATION_SCHEMA_MIGRATION_ID,),
                )
                migration_row = cursor.fetchone()

                cursor.execute(
                    """
                    select source_id, source_type, provider, stale_after_minutes
                    from public.telemetry_sources
                    where source_id = 'irrigation-controller-main'
                    """
                )
                source_row = cursor.fetchone()

        expected_tables = sorted(IRRIGATION_SCHEMA_TABLES)
        missing_tables = [table for table in expected_tables if table not in found_tables]

        if missing_tables or not migration_row or not source_row:
            return {
                "success": False,
                "configured": True,
                "status": "irrigation_schema_missing",
                "migration_id": IRRIGATION_SCHEMA_MIGRATION_ID,
                "migration_applied": bool(migration_row),
                "expected_tables": expected_tables,
                "found_tables": found_tables,
                "missing_tables": missing_tables,
                "irrigation_source_found": bool(source_row),
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
            "irrigation_source": {
                "source_id": source_row[0],
                "source_type": source_row[1],
                "provider": source_row[2],
                "stale_after_minutes": source_row[3],
            },
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "irrigation_schema_check_failed",
            "message": "Irrigation schema check failed.",
            "error_type": exc.__class__.__name__,
        }, 503
