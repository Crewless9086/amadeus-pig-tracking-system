create table if not exists public.oom_sakkie_traces (
    trace_id text primary key,
    channel text not null default '',
    session_id text not null default '',
    user_text text not null default '',
    intent text not null default '',
    confidence numeric(5, 4) not null default 0,
    tool_name text not null default '',
    tool_args_json jsonb not null default '{}'::jsonb,
    tool_result_summary text not null default '',
    tool_result_hash text not null default '',
    answer text not null default '',
    risk_level integer not null default 0,
    stale_warnings_json jsonb not null default '[]'::jsonb,
    links_json jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_traces_created_at
    on public.oom_sakkie_traces (created_at desc);

create index if not exists idx_oom_sakkie_traces_channel_created_at
    on public.oom_sakkie_traces (channel, created_at desc);
