-- Distinguish an immutable historical review superseded by a later review
-- from a customer inbound superseded by a later customer inbound.  This is
-- append-only classification authority only; it grants no customer or farm
-- mutation authority.

alter table public.sam_review_obligation_resolution_events
  drop constraint if exists sam_review_obligation_resolution_events_customer_obligation_status_check;

alter table public.sam_review_obligation_resolution_events
  add constraint sam_review_obligation_resolution_events_customer_obligation_status_check
  check (customer_obligation_status in (
    'active_replan_required','delivered_attempt_requires_content_resolution',
    'completed_by_attributable_supported_reply',
    'corrective_replan_required_after_reply','superseded_by_later_inbound',
    'superseded_by_later_review','quarantined_no_retry',
    'closed_window_reengagement_required','protected_owner_action_required',
    'unknown_fail_closed'
  ));
