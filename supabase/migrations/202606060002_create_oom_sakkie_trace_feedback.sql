create table if not exists public.oom_sakkie_trace_feedback (
    feedback_id text primary key,
    trace_id text not null references public.oom_sakkie_traces(trace_id) on delete cascade,
    feedback_type text not null,
    notes text not null default '',
    reviewed_by text not null default '',
    channel text not null default '',
    created_at timestamptz not null default now(),
    constraint oom_sakkie_trace_feedback_type_check check (
        feedback_type in (
            'correct',
            'wrong_tool',
            'stale_or_missing_data',
            'bad_wording',
            'needs_follow_up'
        )
    )
);

create index if not exists idx_oom_sakkie_trace_feedback_trace_created
    on public.oom_sakkie_trace_feedback(trace_id, created_at desc);

create index if not exists idx_oom_sakkie_trace_feedback_type_created
    on public.oom_sakkie_trace_feedback(feedback_type, created_at desc);
