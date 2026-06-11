create table if not exists public.oom_sakkie_learning_influence_consumption_requests (
    consumption_request_id text primary key,
    proposal_id text not null references public.oom_sakkie_learning_influence_proposals(proposal_id),
    source_result_id text not null,
    status text not null default 'requested_for_consumption_design_review',
    mode text not null default 'learning_influence_consumption_request_only',
    requested_target_kind text not null,
    requested_target_field text not null,
    request_note text not null default '',
    review_note_artifact_json jsonb not null default '{}'::jsonb,
    requested_by text not null default 'owner',
    applies_learning_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    changes_runtime_now boolean not null default false,
    dispatch_enabled boolean not null default false,
    writes boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_learning_consumption_request_mode_check check (
        mode = 'learning_influence_consumption_request_only'
    ),
    constraint oom_sakkie_learning_consumption_request_status_check check (
        status = 'requested_for_consumption_design_review'
    ),
    constraint oom_sakkie_learning_consumption_request_target_kind_check check (
        requested_target_kind in (
            'planning_context_note',
            'routing_hint_review_note',
            'answer_style_review_note'
        )
    ),
    constraint oom_sakkie_learning_consumption_request_target_field_check check (
        length(btrim(requested_target_field)) > 0
    ),
    constraint oom_sakkie_learning_consumption_request_no_apply_check check (
        applies_learning_now = false
        and changes_prompt_now = false
        and changes_runtime_now = false
        and dispatch_enabled = false
        and writes = false
    )
);

create unique index if not exists idx_oom_sakkie_learning_consumption_request_target_once
    on public.oom_sakkie_learning_influence_consumption_requests(
        proposal_id,
        requested_target_kind,
        requested_target_field
    );

create index if not exists idx_oom_sakkie_learning_consumption_requests_created
    on public.oom_sakkie_learning_influence_consumption_requests(created_at desc);

create table if not exists public.oom_sakkie_learning_influence_consumption_events (
    event_id text primary key,
    consumption_request_id text not null references public.oom_sakkie_learning_influence_consumption_requests(consumption_request_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    applies_learning_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    changes_runtime_now boolean not null default false,
    dispatch_enabled boolean not null default false,
    writes boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_learning_consumption_event_type_check check (
        event_type in (
            'review_note',
            'approved_for_design_review',
            'rejected',
            'consumed_for_patch_proposal'
        )
    ),
    constraint oom_sakkie_learning_consumption_event_no_apply_check check (
        applies_learning_now = false
        and changes_prompt_now = false
        and changes_runtime_now = false
        and dispatch_enabled = false
        and writes = false
    )
);

create index if not exists idx_oom_sakkie_learning_consumption_events_request_created
    on public.oom_sakkie_learning_influence_consumption_events(consumption_request_id, created_at desc);

create unique index if not exists idx_oom_sakkie_learning_consumption_consumed_once
    on public.oom_sakkie_learning_influence_consumption_events(consumption_request_id)
    where event_type = 'consumed_for_patch_proposal';

create or replace function public.prevent_oom_sakkie_learning_consumption_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_learning_influence_consumption tables are append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_learning_consumption_requests_update on public.oom_sakkie_learning_influence_consumption_requests;
create trigger prevent_oom_sakkie_learning_consumption_requests_update
    before update on public.oom_sakkie_learning_influence_consumption_requests
    for each row
    execute function public.prevent_oom_sakkie_learning_consumption_mutation();

drop trigger if exists prevent_oom_sakkie_learning_consumption_requests_delete on public.oom_sakkie_learning_influence_consumption_requests;
create trigger prevent_oom_sakkie_learning_consumption_requests_delete
    before delete on public.oom_sakkie_learning_influence_consumption_requests
    for each row
    execute function public.prevent_oom_sakkie_learning_consumption_mutation();

drop trigger if exists prevent_oom_sakkie_learning_consumption_events_update on public.oom_sakkie_learning_influence_consumption_events;
create trigger prevent_oom_sakkie_learning_consumption_events_update
    before update on public.oom_sakkie_learning_influence_consumption_events
    for each row
    execute function public.prevent_oom_sakkie_learning_consumption_mutation();

drop trigger if exists prevent_oom_sakkie_learning_consumption_events_delete on public.oom_sakkie_learning_influence_consumption_events;
create trigger prevent_oom_sakkie_learning_consumption_events_delete
    before delete on public.oom_sakkie_learning_influence_consumption_events
    for each row
    execute function public.prevent_oom_sakkie_learning_consumption_mutation();
