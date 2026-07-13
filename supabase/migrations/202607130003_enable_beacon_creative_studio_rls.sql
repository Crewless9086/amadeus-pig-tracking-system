-- Security hardening for the private Beacon Creative Studio tables.
-- Additive migration only. Do not apply without separate owner approval.
--
-- The Flask backend owns all Creative Studio access through direct Postgres
-- connections. Browser-facing Supabase roles must have no table access, so RLS
-- is enabled without creating anon or authenticated-role policies.

alter table public.beacon_creative_jobs enable row level security;
alter table public.beacon_creative_job_sources enable row level security;
alter table public.beacon_creative_provider_attempts enable row level security;
alter table public.beacon_creative_cost_events enable row level security;
alter table public.beacon_creative_variants enable row level security;
alter table public.beacon_creative_review_events enable row level security;
