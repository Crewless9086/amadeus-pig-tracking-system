alter table public.beacon_facebook_post_execution_events
    drop constraint if exists beacon_facebook_post_execution_events_execution_status_check;

alter table public.beacon_facebook_post_execution_events
    add constraint beacon_facebook_post_execution_events_execution_status_check
    check (execution_status in (
        'not_attempted',
        'facebook_posting_disabled',
        'facebook_page_credentials_missing',
        'owner_confirmation_required',
        'publish_packet_id_required',
        'exact_text_required',
        'channel_not_facebook',
        'selected_image_asset_required',
        'selected_asset_must_be_image',
        'selected_image_asset_not_public_use_approved',
        'selected_image_asset_storage_missing',
        'facebook_image_posting_storage_not_configured',
        'facebook_page_post_sent',
        'facebook_page_post_failed',
        'record_only_before_send'
    ));
