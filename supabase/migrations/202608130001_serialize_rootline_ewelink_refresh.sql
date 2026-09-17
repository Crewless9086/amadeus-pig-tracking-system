alter table app_private.rootline_ewelink_oauth_tokens
    add column if not exists predecessor_token_binding_id text,
    add column if not exists generation bigint;

alter table app_private.rootline_ewelink_oauth_tokens disable trigger trg_rootline_ewelink_tokens_append_only;
with ordered as (
    select token_binding_id,
           row_number() over (order by created_at, token_binding_id) as n,
           lag(token_binding_id) over (order by created_at, token_binding_id) as predecessor
    from app_private.rootline_ewelink_oauth_tokens
)
update app_private.rootline_ewelink_oauth_tokens t
set generation=ordered.n, predecessor_token_binding_id=ordered.predecessor
from ordered where ordered.token_binding_id=t.token_binding_id and t.generation is null;
alter table app_private.rootline_ewelink_oauth_tokens enable trigger trg_rootline_ewelink_tokens_append_only;

alter table app_private.rootline_ewelink_oauth_tokens alter column generation set not null;
create unique index if not exists rootline_ewelink_oauth_tokens_generation_uq
    on app_private.rootline_ewelink_oauth_tokens(generation);
create unique index if not exists rootline_ewelink_oauth_tokens_predecessor_uq
    on app_private.rootline_ewelink_oauth_tokens(predecessor_token_binding_id)
    where predecessor_token_binding_id is not null;

insert into app_private.migration_log(migration_id,description)
values ('202608130001_serialize_rootline_ewelink_refresh',
        'Serialize ROOTLINE eWeLink refresh generations with exact predecessor CAS ordering.')
on conflict (migration_id) do nothing;
