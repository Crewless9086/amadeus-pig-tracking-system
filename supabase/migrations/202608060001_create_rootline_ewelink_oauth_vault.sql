create table if not exists app_private.rootline_ewelink_oauth_states (
    state_digest text primary key check (state_digest ~ '^[0-9a-f]{64}$'),
    principal_digest text not null check (principal_digest ~ '^[0-9a-f]{64}$'),
    nonce_digest text not null check (nonce_digest ~ '^[0-9a-f]{64}$'),
    redirect_uri_digest text not null check (redirect_uri_digest ~ '^[0-9a-f]{64}$'),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists app_private.rootline_ewelink_oauth_tokens (
    token_binding_id text primary key,
    provider_account_digest text not null check (provider_account_digest ~ '^[0-9a-f]{64}$'),
    device_id text not null check (device_id = '100204e9bc'),
    region text not null check (region in ('as','eu','us','cn')),
    access_token_ciphertext text not null,
    refresh_token_ciphertext text not null,
    access_expires_at timestamptz not null,
    refresh_expires_at timestamptz not null,
    response_digest text not null check (response_digest ~ '^[0-9a-f]{64}$'),
    adapter_version text not null check (adapter_version = 'rootline_ewelink_oauth_v1'),
    status_field_names jsonb not null check (jsonb_typeof(status_field_names) = 'array'),
    created_at timestamptz not null
);

drop index if exists app_private.rootline_ewelink_oauth_tokens_response_uq;

create or replace function app_private.rootline_ewelink_tokens_append_only()
returns trigger language plpgsql as $$ begin
    raise exception 'ROOTLINE eWeLink token vault is append-only';
end $$;

drop trigger if exists trg_rootline_ewelink_tokens_append_only
on app_private.rootline_ewelink_oauth_tokens;
create trigger trg_rootline_ewelink_tokens_append_only
before update or delete on app_private.rootline_ewelink_oauth_tokens
for each row execute function app_private.rootline_ewelink_tokens_append_only();

create or replace function app_private.rootline_ewelink_account_binding_guard()
returns trigger language plpgsql as $$ declare existing_account text; begin
    select provider_account_digest into existing_account
      from app_private.rootline_ewelink_oauth_tokens limit 1;
    if existing_account is not null and existing_account <> new.provider_account_digest then
        raise exception 'ROOTLINE eWeLink provider account binding mismatch';
    end if;
    return new;
end $$;

drop trigger if exists trg_rootline_ewelink_account_binding_guard
on app_private.rootline_ewelink_oauth_tokens;
create trigger trg_rootline_ewelink_account_binding_guard
before insert on app_private.rootline_ewelink_oauth_tokens
for each row execute function app_private.rootline_ewelink_account_binding_guard();

revoke all on app_private.rootline_ewelink_oauth_states from public,anon,authenticated;
revoke all on app_private.rootline_ewelink_oauth_tokens from public,anon,authenticated;

insert into app_private.migration_log(migration_id,description)
values ('202608060001_create_rootline_ewelink_oauth_vault',
        'Create single-use ROOTLINE eWeLink OAuth state and encrypted append-only token vault.')
on conflict (migration_id) do nothing;
