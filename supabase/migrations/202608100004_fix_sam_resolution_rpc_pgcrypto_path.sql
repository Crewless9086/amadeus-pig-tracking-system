-- Supabase installs pgcrypto in the protected `extensions` schema.  The
-- service-only resolution RPC originally pinned search_path to `public`, so
-- service_role could not resolve digest().  Keep the security-definer search
-- path explicit and narrow while making the reviewed hash function available.

alter function public.record_sam_review_obligation_resolution(jsonb)
  set search_path = pg_catalog, extensions, public;
