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
                cursor.execute("""select token_binding_id,generation
                    from app_private.rootline_ewelink_oauth_tokens
                    order by generation desc,created_at desc,token_binding_id desc limit 1""")
                predecessor = cursor.fetchone()
                cursor.execute("""insert into app_private.rootline_ewelink_oauth_tokens
                    (token_binding_id,provider_account_digest,device_id,region,
                     access_token_ciphertext,refresh_token_ciphertext,access_expires_at,
                     refresh_expires_at,response_digest,adapter_version,status_field_names,created_at,
                     predecessor_token_binding_id,generation)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    on conflict (token_binding_id) do nothing returning token_binding_id""",
                    (item["token_binding_id"],item["provider_account_digest"],item["device_id"],
                     item["region"],item["access_token_ciphertext"],item["refresh_token_ciphertext"],
                     item["access_expires_at"],item["refresh_expires_at"],item["response_digest"],
                     item["adapter_version"],__import__("json").dumps(item["status_field_names"]),
                     item["created_at"], predecessor[0] if predecessor else None,
                     predecessor[1] + 1 if predecessor else 1))
                return cursor.fetchone() is not None

    def latest(self):
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select token_binding_id,provider_account_digest,device_id,region,
                    access_token_ciphertext,refresh_token_ciphertext,access_expires_at,
                    refresh_expires_at,response_digest,adapter_version,created_at
                    from app_private.rootline_ewelink_oauth_tokens
                    order by generation desc, created_at desc, token_binding_id desc limit 1""")
                row = cursor.fetchone()
        if not row:
            return None
        names = ("token_binding_id", "provider_account_digest", "device_id", "region",
                 "access_token_ciphertext", "refresh_token_ciphertext", "access_expires_at",
                 "refresh_expires_at", "response_digest", "adapter_version", "created_at")
        return dict(zip(names, row))

    def rotate_exact(self, predecessor_id, build_generation):
        """Serialize provider rotation and CAS the result to the exact predecessor.

        ``build_generation`` is invoked at most once and only while the durable
        account-binding row is locked.  If commit acknowledgement is lost, the
        exact encrypted result is reconciled without another provider request.
        """
        import json
        import psycopg

        pending = None
        try:
            with psycopg.connect(self.database_url, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""select provider_account_digest
                        from app_private.rootline_ewelink_account_binding
                        where binding_key=true for update""")
                    binding = cursor.fetchone()
                    cursor.execute("""select token_binding_id,provider_account_digest,device_id,region,
                        access_token_ciphertext,refresh_token_ciphertext,access_expires_at,
                        refresh_expires_at,response_digest,adapter_version,created_at,generation
                        from app_private.rootline_ewelink_oauth_tokens
                        order by generation desc,created_at desc,token_binding_id desc limit 1""")
                    row = cursor.fetchone()
                    if not row or row[0] != predecessor_id:
                        return None
                    names = ("token_binding_id", "provider_account_digest", "device_id", "region",
                             "access_token_ciphertext", "refresh_token_ciphertext", "access_expires_at",
                             "refresh_expires_at", "response_digest", "adapter_version", "created_at",
                             "generation")
                    current = dict(zip(names, row))
                    if not binding or binding[0] != current["provider_account_digest"]:
                        raise ValueError("ewelink_provider_account_binding_mismatch")
                    pending = dict(build_generation(current))
                    pending["predecessor_token_binding_id"] = predecessor_id
                    pending["generation"] = current["generation"] + 1
                    self._insert_generation(cursor, pending, json)
            return pending
        except Exception:
            if pending is None:
                raise
            # The commit may have succeeded even though its acknowledgement was
            # lost. Reconcile the deterministic identity before attempting the
            # same insert; never call the provider again.
            return self._recover_generation(pending)

    def _recover_generation(self, item):
        import json
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select token_binding_id from app_private.rootline_ewelink_oauth_tokens
                    where generation=%s and token_binding_id=%s""",
                    (item["generation"], item["token_binding_id"]))
                if cursor.fetchone():
                    return item
                cursor.execute("""select token_binding_id from app_private.rootline_ewelink_oauth_tokens
                    order by generation desc,created_at desc,token_binding_id desc limit 1 for update""")
                latest = cursor.fetchone()
                if not latest or latest[0] != item["predecessor_token_binding_id"]:
                    raise RuntimeError("ewelink_refresh_recovery_conflict")
                self._insert_generation(cursor, item, json)
        return item

    @staticmethod
    def _insert_generation(cursor, item, json_module):
        cursor.execute("""insert into app_private.rootline_ewelink_oauth_tokens
            (token_binding_id,provider_account_digest,device_id,region,
             access_token_ciphertext,refresh_token_ciphertext,access_expires_at,
             refresh_expires_at,response_digest,adapter_version,status_field_names,created_at,
             predecessor_token_binding_id,generation)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (item["token_binding_id"], item["provider_account_digest"], item["device_id"],
             item["region"], item["access_token_ciphertext"], item["refresh_token_ciphertext"],
             item["access_expires_at"], item["refresh_expires_at"], item["response_digest"],
             item["adapter_version"], json_module.dumps(item.get("status_field_names", [])),
             item["created_at"], item["predecessor_token_binding_id"], item["generation"]))
