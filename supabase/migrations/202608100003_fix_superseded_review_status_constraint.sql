-- PostgreSQL truncated the original generated check-constraint name to 63
-- bytes.  Migration 202608100002 therefore did not replace that existing
-- constraint.  Drop both possible spellings and install a deliberately short,
-- stable name.  The table is still empty at this correction boundary.

alter table public.sam_review_obligation_resolution_events
  drop constraint if exists sam_review_obligation_resoluti_customer_obligation_status_check;

alter table public.sam_review_obligation_resolution_events
  drop constraint if exists sam_review_obligation_resolution_events_customer_obligation_status_check;

alter table public.sam_review_obligation_resolution_events
  drop constraint if exists sam_review_obligation_status_check_v2;

alter table public.sam_review_obligation_resolution_events
  add constraint sam_review_obligation_status_check_v2
  check (customer_obligation_status in (
    'active_replan_required','delivered_attempt_requires_content_resolution',
    'completed_by_attributable_supported_reply',
    'corrective_replan_required_after_reply','superseded_by_later_inbound',
    'superseded_by_later_review','quarantined_no_retry',
    'closed_window_reengagement_required','protected_owner_action_required',
    'unknown_fail_closed'
  ));
