create or replace function public.prevent_oom_sakkie_trace_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'Oom Sakkie trace tables are append-only. % is not allowed on %.', tg_op, tg_table_name;
end;
$$;

drop trigger if exists prevent_oom_sakkie_traces_update on public.oom_sakkie_traces;
create trigger prevent_oom_sakkie_traces_update
    before update on public.oom_sakkie_traces
    for each row
    execute function public.prevent_oom_sakkie_trace_mutation();

drop trigger if exists prevent_oom_sakkie_traces_delete on public.oom_sakkie_traces;
create trigger prevent_oom_sakkie_traces_delete
    before delete on public.oom_sakkie_traces
    for each row
    execute function public.prevent_oom_sakkie_trace_mutation();

drop trigger if exists prevent_oom_sakkie_trace_feedback_update on public.oom_sakkie_trace_feedback;
create trigger prevent_oom_sakkie_trace_feedback_update
    before update on public.oom_sakkie_trace_feedback
    for each row
    execute function public.prevent_oom_sakkie_trace_mutation();

drop trigger if exists prevent_oom_sakkie_trace_feedback_delete on public.oom_sakkie_trace_feedback;
create trigger prevent_oom_sakkie_trace_feedback_delete
    before delete on public.oom_sakkie_trace_feedback
    for each row
    execute function public.prevent_oom_sakkie_trace_mutation();
