import os


DATABASE_URL_ENV = "DATABASE_URL"


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
