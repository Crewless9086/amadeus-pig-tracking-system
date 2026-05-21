# Supabase Migrations

Plain SQL migrations for the Amadeus Farm Supabase/Postgres foundation.

Rules:

- Keep migration files in this folder.
- Use timestamped filenames, for example `202605210001_create_orders_schema.sql`.
- Review every migration before running it in Supabase.
- Do not store database passwords, connection strings, service-role keys, or anon keys in this folder.
- Do not run production imports until the backup, shadow-read, comparison, and rollback gates are accepted.

Current state:

- `202605210001_foundation_migration_log.sql` is the first baseline migration.
- It creates only the internal `app_private.migration_log` table.
- It does not create order, pig, weight, breeding, weather, Sunsynk, irrigation, or customer business tables.
- `202605210002_create_order_sales_tables.sql` is the first empty business-table migration.
- It creates only the seven Phase 10.2 order/sales boundary tables.
- It imports no data and does not change live backend order reads/writes.

Manual run process for Phase 10.1B:

1. Open Supabase SQL Editor.
2. Open `supabase/migrations/202605210001_foundation_migration_log.sql` from this repo.
3. Paste the full SQL into Supabase SQL Editor.
4. Run it once.
5. Open `/health/database/foundation` on the deployed backend.
6. Confirm it returns `success = true`, `status = ok`, and migration ID `202605210001_foundation_migration_log`.

Manual run process for Phase 10.2A:

1. Deploy the backend containing `/health/database/order-schema`.
2. Open Supabase SQL Editor.
3. Open `supabase/migrations/202605210002_create_order_sales_tables.sql` from this repo.
4. Paste the full SQL into Supabase SQL Editor.
5. Run it once.
6. Open `/health/database/order-schema` on the deployed backend.
7. Confirm it returns `success = true`, `status = ok`, and all seven expected tables.
