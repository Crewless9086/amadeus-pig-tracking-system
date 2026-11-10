"""Least-privilege, zero-command eWeLink device readback."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import re
import time
import urllib.parse

from modules.telemetry.rootline_ewelink_oauth import (
    ADAPTER_VERSION, REGION_HOSTS, OAuthFailure, _bind_account_device,
    _digest, _encrypt, _provider_request, _token_key, decrypt_access_token,
    decrypt_refresh_token, normalize_device_readback,
)
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline, commissioned_registered_device_baseline,
)
from modules.telemetry.rootline_device_registry import rootline_device_registry


def read_current_device(*, token_store, environ=None, http_request=None, now=None):
    source = environ if environ is not None else os.environ
    return _read_bound_device(
        expected=str(source.get("EWELINK_EXPECTED_DEVICE_ID") or ""),
        token_store=token_store,
        source=source,
        http_request=http_request,
        now=now,
        commissioned_baseline=commissioned_controller_baseline(),
        registered_discovery_only=False,
    )


def read_registered_device(device_id, *, token_store, environ=None,
                           http_request=None, now=None, commissioning_connect_factory=None):
    """Read an exact registry-bound device without expanding command authority."""
    source = environ if environ is not None else os.environ
    requested = str(device_id or "").strip()
    contracts = [row for row in rootline_device_registry().values()
                 if row.get("device_id") == requested]
    if (not requested or not contracts
            or any(row.get("provider_account_binding") != "ewelink_owner_account"
                   for row in contracts)):
        raise OAuthFailure("ewelink_registered_device_rejected")
    result = _read_bound_device(
        expected=requested,
        token_store=token_store,
        source=source,
        http_request=http_request,
        now=now,
        commissioned_baseline=commissioned_registered_device_baseline(requested),
        registered_discovery_only=False,
    )
    if requested == "1002851416":
        connect = commissioning_connect_factory
        database_url = str(source.get("DATABASE_URL")
            or getattr(token_store, "database_url", "") or "").strip()
        if connect is None and database_url:
            from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
            def connect():
                return connect_bounded_rootline_postgres(database_url=database_url, read_only=True)
        if callable(connect):
            from modules.telemetry.rootline_ewelink_commissioned_baseline import canonical_borehole_control_paths
            try:
                result = canonical_borehole_control_paths(result, connect_factory=connect)
            except Exception:
                # Keep unsupported facts Unknown when proof cannot be resolved.
                pass
            material = {k: v for k, v in result.items() if k != "response_digest"}
            result["response_digest"] = sha256(json.dumps(material, sort_keys=True,
                separators=(",", ":"), default=str).encode()).hexdigest()
    return result


def _read_bound_device(*, expected, token_store, source, http_request, now,
                       commissioned_baseline, registered_discovery_only):
    if str(source.get("EWELINK_READBACK_ENABLED") or "").lower() != "true":
        raise OAuthFailure("ewelink_readback_disabled")
    now = now or datetime.now(timezone.utc)
    record = token_store.latest()
    anchor = str(source.get("EWELINK_EXPECTED_DEVICE_ID") or "")
    if (not record or record.get("device_id") != anchor
            or record.get("adapter_version") != ADAPTER_VERSION
            or record.get("region") not in REGION_HOSTS):
        raise OAuthFailure("ewelink_readback_token_unavailable")
    from modules.telemetry.rootline_ewelink_request_budget import snapshot_group
    request_source = dict(source)
    if not request_source.get("DATABASE_URL"):
        request_source["DATABASE_URL"] = getattr(token_store, "database_url", "")
    with snapshot_group(expected_device=expected, environ=request_source, region=record["region"]) as group:
        result = _read_snapshot(expected=expected, token_store=token_store,
            source=request_source, http_request=http_request, now=now, record=record,
            commissioned_baseline=commissioned_baseline,
            registered_discovery_only=registered_discovery_only)
        group["normalized_complete"] = True
        return result


def _read_snapshot(*, expected, token_store, source, http_request, now, record,
                   commissioned_baseline, registered_discovery_only):
    request = http_request or _provider_request
    token_refreshed = False
    if record.get("access_expires_at") <= now:
        record = _refresh_token_generation(record, token_store=token_store,
            source=source, request=request, now=now)
        token_refreshed = True
    access = decrypt_access_token(record, source)
    host = REGION_HOSTS[record["region"]]
    family = request("GET", host + "/v2/family", mode="bearer", token=access, environ=source)
    return _read_device_status(expected=expected, source=source, request=request,
        now=now, record=record, access=access, family=family,
        commissioned_baseline=commissioned_baseline,
        registered_discovery_only=registered_discovery_only,
        token_refreshed=token_refreshed, fresh_receipt=http_request is None)


def _read_device_status(*, expected, source, request, now, record, access, family,
                        commissioned_baseline, registered_discovery_only,
                        token_refreshed, fresh_receipt):
    """Both output-bearing requests stay together in the caller's read phase."""
    host = REGION_HOSTS[record["region"]]
    things = request("GET", host + "/v2/device/thing?num=0", mode="bearer", token=access, environ=source)
    account, device = _bind_account_device(family, things, expected, source)
    if not __import__("hmac").compare_digest(_digest(account), record["provider_account_digest"]):
        raise OAuthFailure("ewelink_account_binding_changed")
    request_source = dict(source)
    request_source["EWELINK_EXPECTED_DEVICE_ID"] = expected
    status = request("GET", host + "/v2/device/thing/status?" +
        urllib.parse.urlencode({"type": 1, "id": expected}),
        mode="bearer", token=access, environ=request_source)
    # Production receipts use the clock AFTER all provider I/O.  An explicitly
    # supplied synthetic requester retains its deterministic fixture clock.
    retrieved_at = datetime.now(timezone.utc) if fresh_receipt else now
    result = normalize_device_readback(device=device, status=status, retrieved_at=retrieved_at,
        commissioned_baseline=commissioned_baseline)
    if result["device_id"] != expected:
        raise OAuthFailure("ewelink_readback_device_mismatch")
    safe_material = {key: value for key, value in result.items() if key != "response_digest"}
    result["response_digest"] = sha256(json.dumps(safe_material, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    result["provider_calls"] = 4 if token_refreshed else 3
    result["provider_control_calls"] = 0
    result["token_refreshed"] = token_refreshed
    result["autonomous_control_enabled"] = False
    result["registered_discovery_only"] = registered_discovery_only
    return result


def _refresh_token_generation(record, *, token_store, source, request, now):
    """Rotate through the store's serialized exact-predecessor CAS lifecycle."""
    def build(locked):
        if not locked.get("refresh_expires_at") or locked["refresh_expires_at"] <= now:
            raise OAuthFailure("ewelink_refresh_token_unavailable")
        refresh = decrypt_refresh_token(locked, source)
        data = request("POST", REGION_HOSTS[locked["region"]] + "/v2/user/refresh",
            body={"rt": refresh}, mode="signed", environ=source)
        access = str(data.get("at") or "")
        rotated_refresh = str(data.get("rt") or "")
        if not access or not rotated_refresh:
            raise OAuthFailure("ewelink_refresh_response_incomplete")
        key = _token_key(source)
        generation_digest = __import__("hmac").new(
            key, (access + "\0" + rotated_refresh).encode(), __import__("hashlib").sha256
        ).hexdigest()
        aad = (f"{locked['region']}|{locked['provider_account_digest']}|"
               f"{locked['device_id']}|{locked['adapter_version']}").encode()
        return {
        **locked,
        "token_binding_id": "ROOTLINE-EWELINK-" + generation_digest[:24].upper(),
        "access_token_ciphertext": _encrypt(access, key, aad),
        "refresh_token_ciphertext": _encrypt(rotated_refresh, key, aad),
        "access_expires_at": now + timedelta(days=30),
        "refresh_expires_at": now + timedelta(days=60),
        "response_digest": _digest(json.dumps({
            "previous_generation": record["token_binding_id"],
            "access_expires_at": (now + timedelta(days=30)).isoformat(),
            "refresh_expires_at": (now + timedelta(days=60)).isoformat(),
        }, sort_keys=True, separators=(",", ":"))),
        "status_field_names": [],
        "created_at": now,
        }
    try:
        refreshed = token_store.rotate_exact(record["token_binding_id"], build)
    except OAuthFailure:
        raise
    except Exception as exc:
        raise OAuthFailure("ewelink_refresh_recovery_required") from exc
    if refreshed is None:
        latest = token_store.latest()
        if not latest:
            raise OAuthFailure("ewelink_refresh_recovery_required")
        refreshed = latest
    return refreshed


class NoSendReadUnavailable(RuntimeError):
    """A private read phase failed; raw database/provider errors never escape."""
    def __init__(self, stage, reason):
        self.stage, self.reason = stage, reason
        super().__init__("no_send_" + stage + "_" + reason)


def no_send_failure(exc, stage):
    if isinstance(exc, NoSendReadUnavailable):
        return exc
    from modules.oom_sakkie.bounded_postgres_read import is_database_unavailable
    from modules.telemetry.rootline_ewelink_request_budget import RequestBudgetUnavailable
    if is_database_unavailable(exc):
        reason = "database_unavailable"
    elif isinstance(exc, TimeoutError):
        reason = "deadline"
    elif isinstance(exc, (OAuthFailure, RequestBudgetUnavailable)):
        value = str(exc)
        reason = value if re.fullmatch(r"[a-z][a-z0-9_]{0,95}", value) else "read_unavailable"
    else:
        reason = "unavailable"
    return NoSendReadUnavailable(stage, reason)


_TOKEN_IDENTITY = ("token_binding_id", "provider_account_digest", "device_id",
                   "region", "access_expires_at", "adapter_version")


def _validate_prepared_record(record, source):
    if (not isinstance(record, dict) or not record.get("token_binding_id")
            or record.get("device_id") != source.get("EWELINK_EXPECTED_DEVICE_ID")
            or record.get("adapter_version") != ADAPTER_VERSION
            or record.get("region") not in REGION_HOSTS
            or not isinstance(record.get("access_expires_at"), datetime)
            or record["access_expires_at"].tzinfo is None):
        raise OAuthFailure("ewelink_readback_token_unavailable")


class _PreparedNoSendRead:
    """One invocation, one credential/family context; never a cached output."""
    def __init__(self, *, binding, token_store, source, record, family, access,
                 request, group, token_refreshed):
        self.binding = deepcopy(binding)
        self.token_store, self.source = token_store, source
        self._record, self._family, self._access = record, family, access
        self._request, self._group = request, group
        self._refreshed, self._active, self._used = token_refreshed, True, False
        self._complete, self._finalized = False, False
        self._pair = None
        self.stage = "prepared"

    def read_locked(self, *, binding, connection, deadline):
        from modules.telemetry.rootline_cycle_budget import cycle_budget
        from modules.telemetry.rootline_ewelink_request_budget import current_duty, request_timeout, _NoSendPair
        if (not self._active or self._used or binding != self.binding
                or current_duty().get("execution_id") != binding.get("execution_id")):
            raise NoSendReadUnavailable("context", "changed_or_consumed")
        self._used = True
        self._group["deadline"] = min(self._group["deadline"], time.monotonic() +
            max(0, (deadline-datetime.now(timezone.utc)).total_seconds()))
        with cycle_budget(deadline=self._group["deadline"]):
            try:
                request_timeout()
                self.stage = "token_current"
                identity_reader = getattr(self.token_store, "latest_identity", None)
                current = (identity_reader(connection=connection) if callable(identity_reader)
                           else self.token_store.latest())
                if (not current or any(current.get(key) != self._record.get(key)
                        for key in _TOKEN_IDENTITY)):
                    raise OAuthFailure("ewelink_prepared_token_changed")
                if current["access_expires_at"] <= deadline:
                    raise OAuthFailure("ewelink_prepared_token_expires_before_read")
                request_timeout()
                # Capture credentials/metadata in this invocation's closure so
                # a late worker never consults a closed/reused prepared object.
                record, access, family, source = self._record, self._access, self._family, self.source
                original_request = self._request
                pair = self._pair = _NoSendPair(source=source, binding=binding,
                    token_identity=tuple(record.get(key) for key in _TOKEN_IDENTITY), group=self._group)
                def request(method, url, **kwargs):
                    pair.check_active()
                    if kwargs.get("token") != access:
                        pair.abandon()
                        raise OAuthFailure("ewelink_prepared_token_changed")
                    self.stage = ("device_status" if urllib.parse.urlparse(url).path ==
                        "/v2/device/thing/status" else "device_list")
                    return original_request(method, url, **kwargs)
                result = pair.run(lambda: _read_device_status(expected=binding["device_id"],
                    source=source, request=request, now=datetime.now(timezone.utc),
                    record=record, access=access, family=family,
                    commissioned_baseline=commissioned_registered_device_baseline(binding["device_id"]),
                    registered_discovery_only=False, token_refreshed=self._refreshed,
                    fresh_receipt=True))
                request_timeout()
                self._complete = True
                self.stage = "proof_received"
                return result
            except Exception as exc:
                # A canonical/token precondition is not a provider failure. The
                # ordinary request wrapper already records genuine HTTP failure.
                group = self._group
                if (self.stage != "token_current" and group["budget"] is not None
                        and not group["failed"]):
                    group["failed"] = True
                    try:
                        request_timeout()
                        group["budget"].fail_snapshot(group)
                    except Exception:
                        pass
                raise no_send_failure(exc, self.stage) from None

    def after_commit(self, cleanup):
        """The owning store calls this only after its terminal commit acknowledges."""
        from modules.telemetry.rootline_cycle_budget import cycle_budget
        from modules.telemetry.rootline_ewelink_request_budget import request_timeout
        if not self._active or not self._complete or self._finalized:
            return "retained_incomplete_context"
        self._finalized = True
        try:
            with cycle_budget(deadline=self._group["deadline"]):
                request_timeout()
                self._group["normalized_complete"] = True
                if self._group["budget"] is not None:
                    self._group["budget"].complete_snapshot(self._group)
                request_timeout()
                cleanup()
            return "completed"
        except Exception:
            # Canonical truth is already acknowledged. Charges/holds can be
            # discharged by existing terminal reconciliation on a later cycle.
            return "retained_for_reconciliation"
        finally:
            self._group["normalized_complete"] = False

    def close(self):
        if self._pair is not None:
            self._pair.abandon(failed=not self._complete)
        self._active = False
        self._record = self._family = self._access = None


@contextmanager
def prepare_registered_no_send_read(*, binding, token_store, environ=None,
                                    http_request=None):
    """Prepare authentication/family only; device and status require the locked phase."""
    from modules.telemetry.rootline_cycle_budget import cycle_budget, on_deadline, work_deadline
    from modules.telemetry.rootline_ewelink_request_budget import GROUP_SECONDS, snapshot_group
    source = dict(environ if environ is not None else os.environ)
    if not source.get("DATABASE_URL"):
        source["DATABASE_URL"] = getattr(token_store, "database_url", "")
    expected, channel = binding.get("device_id"), binding.get("channel")
    contracts = [row for row in rootline_device_registry().values()
        if row.get("device_id") == expected and row.get("channel") == channel]
    if (not expected or type(channel) is not int or not contracts
            or any(row.get("provider_account_binding") != "ewelink_owner_account"
                for row in contracts)):
        raise NoSendReadUnavailable("preparation", "registered_target_rejected")
    if str(source.get("EWELINK_READBACK_ENABLED") or "").lower() != "true":
        raise NoSendReadUnavailable("preparation", "readback_disabled")
    parent = work_deadline() if work_deadline() is not None else on_deadline()
    deadline = time.monotonic()+GROUP_SECONDS
    if parent is not None:
        deadline = min(deadline, parent)
    prepared = None
    stage = "token_lookup"
    try:
        with cycle_budget(deadline=deadline):
            record = token_store.latest()
            _validate_prepared_record(record, source)
            with snapshot_group(expected_device=expected, environ=source,
                    region=record["region"], deadline=deadline) as group:
                # Keep normalized_complete false until the canonical commit is
                # acknowledged. A partial/abandoned group never heals a hold.
                request = http_request or _provider_request
                refreshed = record["access_expires_at"] <= datetime.now(timezone.utc)
                if refreshed:
                    stage = "token_refresh"
                    record = _refresh_token_generation(record, token_store=token_store,
                        source=source, request=request, now=datetime.now(timezone.utc))
                    _validate_prepared_record(record, source)
                access = decrypt_access_token(record, source)
                stage = "family"
                family = request("GET", REGION_HOSTS[record["region"]]+"/v2/family",
                    mode="bearer", token=access, environ=source)
                prepared = _PreparedNoSendRead(binding=binding, token_store=token_store,
                    source=source, record=deepcopy(record), family=deepcopy(family),
                    access=access, request=request, group=group, token_refreshed=refreshed)
                yield prepared
    except Exception as exc:
        raise no_send_failure(exc, stage) from None
    finally:
        if prepared is not None:
            prepared.close()
