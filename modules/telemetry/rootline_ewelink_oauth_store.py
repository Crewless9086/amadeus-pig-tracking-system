"""PostgreSQL persistence for single-use OAuth state and encrypted tokens."""

import os


class PostgresOAuthStateStore:
    def __init__(self, database_url=None):
        self.database_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()

    def create(self, item):
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into app_private.rootline_ewelink_oauth_states
                    (state_digest,principal_digest,nonce_digest,redirect_uri_digest,expires_at)
                    values (%s,%s,%s,%s,%s)""", (item["state_digest"], item["principal_digest"],
                    item["nonce_digest"], item["redirect_uri_digest"], item["expires_at"]))

    def consume(self, state_digest, now):
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""update app_private.rootline_ewelink_oauth_states
                    set consumed_at=%s where state_digest=%s and consumed_at is null
                      and expires_at >= %s
                    returning principal_digest,nonce_digest,redirect_uri_digest""", (now, state_digest, now))
                row = cursor.fetchone()
        return ({"principal_digest": row[0], "nonce_digest": row[1],
                 "redirect_uri_digest": row[2]} if row else None)


class PostgresOAuthTokenStore:
    def __init__(self, database_url=None):
        self.database_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()

    def append(self, item):
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into app_private.rootline_ewelink_account_binding
                    (binding_key,provider_account_digest) values (true,%s)
                    on conflict (binding_key) do nothing""", (item["provider_account_digest"],))
                cursor.execute("""select provider_account_digest
                    from app_private.rootline_ewelink_account_binding
                    where binding_key=true for update""")
                binding = cursor.fetchone()
                if not binding or binding[0] != item["provider_account_digest"]:
                    raise ValueError("ewelink_provider_account_binding_mismatch")
                cursor.execute("""insert into app_private.rootline_ewelink_oauth_tokens
                    (token_binding_id,provider_account_digest,device_id,region,
                     access_token_ciphertext,refresh_token_ciphertext,access_expires_at,
                     refresh_expires_at,response_digest,adapter_version,status_field_names,created_at)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    on conflict (token_binding_id) do nothing returning token_binding_id""",
                    (item["token_binding_id"],item["provider_account_digest"],item["device_id"],
                     item["region"],item["access_token_ciphertext"],item["refresh_token_ciphertext"],
                     item["access_expires_at"],item["refresh_expires_at"],item["response_digest"],
                     item["adapter_version"],__import__("json").dumps(item["status_field_names"]),
                     item["created_at"]))
                return cursor.fetchone() is not None
