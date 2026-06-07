alter table public.oom_sakkie_traces
    add column if not exists safety_notes_json jsonb not null default '[]'::jsonb;
