insert into public.charlie_delegation_policies (
    policy_id, capability, authority_tier, enabled, max_actions, max_cost,
    rollback_required, deterministic_gate_required, granted_by, metadata_json
) values
    ('POLICY-CORE-DELEGATED-REVIEW', 'core.review_delegate', 'auto', true, 1000, 0, true, true, 'charl',
     '{"scope":"green_low_risk_pr_ready_only","protected_actions":"owner_required","approved_program":"charlie_delegated_governance"}'::jsonb),
    ('POLICY-CORE-QUEUE-SELECT', 'core.queue_select', 'auto', true, 1000, 0, true, true, 'charl',
     '{"scope":"low_risk_new_missions_goal_ranked_max_three","protected_actions":"owner_required","approved_program":"charlie_delegated_governance"}'::jsonb)
on conflict (capability, authority_tier) do update set
    enabled = excluded.enabled,
    metadata_json = excluded.metadata_json,
    updated_at = now();

insert into app_private.migration_log (migration_id, description)
values ('202607170003_add_charlie_delegated_review_policies', 'Authorize bounded CHARLIE delegated review and goal-ranked queue selection for low-risk CORE missions.')
on conflict (migration_id) do nothing;
