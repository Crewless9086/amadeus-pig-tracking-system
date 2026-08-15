alter table public.litters
    add column if not exists first_treatment_skipped_at timestamptz,
    add column if not exists first_treatment_skipped_by text,
    add column if not exists first_treatment_skip_reason text;

alter table public.litters
    drop constraint if exists litter_first_treatment_skip_complete_check;

alter table public.litters
    add constraint litter_first_treatment_skip_complete_check check (
        (first_treatment_skipped_at is null and first_treatment_skipped_by is null)
        or (first_treatment_skipped_at is not null and nullif(btrim(first_treatment_skipped_by), '') is not null)
    );
