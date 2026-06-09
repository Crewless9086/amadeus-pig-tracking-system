alter table public.oom_sakkie_agent_dry_run_results
    drop constraint if exists oom_sakkie_agent_dry_run_result_mode_check;

alter table public.oom_sakkie_agent_dry_run_results
    drop constraint if exists oom_sakkie_agent_dry_run_result_status_check;

alter table public.oom_sakkie_agent_dry_run_results
    drop constraint if exists oom_sakkie_agent_dry_run_result_no_execution_check;

alter table public.oom_sakkie_agent_dry_run_results
    add constraint oom_sakkie_agent_dry_run_result_mode_check check (
        mode in ('dry_run_result_review_only', 'single_shot_sentinel_advisory_result')
    );

alter table public.oom_sakkie_agent_dry_run_results
    add constraint oom_sakkie_agent_dry_run_result_status_check check (
        status in ('recorded_for_owner_review', 'recorded_from_single_shot_sentinel_llm')
    );

alter table public.oom_sakkie_agent_dry_run_results
    add constraint oom_sakkie_agent_dry_run_result_execution_boundary_check check (
        (
            mode = 'dry_run_result_review_only'
            and status = 'recorded_for_owner_review'
            and runs_specialist = false
            and dispatch_enabled = false
            and runs_specialist_llm = false
            and runs_specialist_tools = false
            and writes = false
            and applies_runtime_change = false
        )
        or
        (
            mode = 'single_shot_sentinel_advisory_result'
            and status = 'recorded_from_single_shot_sentinel_llm'
            and specialist_slug = 'sentinel'
            and runs_specialist = true
            and dispatch_enabled = false
            and runs_specialist_llm = true
            and runs_specialist_tools = false
            and writes = false
            and applies_runtime_change = false
        )
    );
