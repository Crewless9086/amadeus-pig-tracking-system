create table if not exists app_private.herdmaster_auction_confirmation_claims (
    operation_id text primary key,
    preview_hash text not null,
    evidence_generation text not null,
    owner_user_id text not null,
    private_chat_id text not null,
    provider_message_id text not null unique,
    provider_timestamp timestamptz not null,
    confirmation_text_sha256 text not null,
    confirmation_id text not null unique,
    created_at timestamptz not null default now(),
    constraint herdmaster_auction_confirmation_owner_chat_check
        check (owner_user_id = private_chat_id),
    constraint herdmaster_auction_confirmation_digest_check
        check (confirmation_text_sha256 ~ '^[0-9a-f]{64}$')
);

revoke all on app_private.herdmaster_auction_confirmation_claims from public, anon, authenticated;
