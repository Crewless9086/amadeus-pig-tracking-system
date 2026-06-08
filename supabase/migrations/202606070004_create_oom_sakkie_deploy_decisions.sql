create table if not exists public.oom_sakkie_deploy_decisions (
    deploy_decision_id text primary key,
    patch_proposal_id text not null references public.oom_sakkie_patch_proposals(patch_proposal_id),
    decision_type text not null,
    environment text not null default 'local',
    notes text not null default '',
    verification_summary text not null default '',
    approved_by text not null default 'owner',
    runs_deploy boolean not null default false,
    deploys_now boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_deploy_decision_type_check check (
        decision_type in ('approved_for_manual_deploy', 'rejected', 'deferred', 'review_note')
    ),
    constraint oom_sakkie_deploy_decisions_record_only_check check (
        runs_deploy = false and deploys_now = false
    )
);

create index if not exists idx_oom_sakkie_deploy_decisions_patch_created
    on public.oom_sakkie_deploy_decisions(patch_proposal_id, created_at desc);

create index if not exists idx_oom_sakkie_deploy_decisions_created_at
    on public.oom_sakkie_deploy_decisions(created_at desc);

create or replace function public.prevent_oom_sakkie_deploy_decision_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_deploy_decisions is append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_deploy_decisions_update on public.oom_sakkie_deploy_decisions;
create trigger prevent_oom_sakkie_deploy_decisions_update
    before update on public.oom_sakkie_deploy_decisions
    for each row
    execute function public.prevent_oom_sakkie_deploy_decision_mutation();

drop trigger if exists prevent_oom_sakkie_deploy_decisions_delete on public.oom_sakkie_deploy_decisions;
create trigger prevent_oom_sakkie_deploy_decisions_delete
    before delete on public.oom_sakkie_deploy_decisions
    for each row
    execute function public.prevent_oom_sakkie_deploy_decision_mutation();
