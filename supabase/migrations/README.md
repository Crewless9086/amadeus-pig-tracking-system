# Supabase Migrations

Plain SQL migrations for the Amadeus Farm Supabase/Postgres foundation.

Rules:

- Keep migration files in this folder.
- Use timestamped filenames, for example `202605210001_create_orders_schema.sql`.
- Review every migration before running it in Supabase.
- Do not store database passwords, connection strings, service-role keys, or anon keys in this folder.
- Do not run production imports until the backup, shadow-read, comparison, and rollback gates are accepted.

Current state:

- No schema migrations have been added yet.
- Phase 10.1 uses this folder only to establish the migration location.
