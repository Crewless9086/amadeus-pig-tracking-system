"""Native zeroconf receipt adapter and one-shot, read-only getState query."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta
import hashlib
import ipaddress
import json
import time

from zeroconf import DNSText, RecordUpdateListener, current_time_millis
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .protocol import DEVICES, MAX_BYTES, InvalidObservation, ObserverState, decode, digest, need, parse_txt, query_payload


class EndpointDiscovery:
    """One explicit attempt's routing metadata; never switch-state evidence."""
    service_type = "_ewelink._tcp.local."

    def __init__(self, shared):
        self.shared = shared

    def records(self, name, kind):
        now = current_time_millis()
        return [record for record in self.shared.cache.get_all_by_details(name, kind, 1)
            if record.ttl > 0 and record.created <= now and not record.is_expired(now)]

    def binding(self, identity):
        need(identity in DEVICES and not self.shared.done, "discovery_unavailable")
        name = f"ewelink_{identity}.{self.service_type}"
        services, texts = self.records(name, 33), self.records(name, 16)
        need(len(services) == len(texts) == 1, "discovery_partial_or_conflicting")
        service, text = services[0], bytes(texts[0].text)
        need(0 < len(text) <= MAX_BYTES, "discovery_identity_unproven")
        # ServiceInfo.properties silently collapses duplicate TXT keys. Parse
        # original metadata bytes strictly; never decrypt or ingest this cache.
        fields, offset = {}, 0
        while offset < len(text):
            size = text[offset]
            offset += 1
            need(size > 0 and offset + size <= len(text), "discovery_identity_unproven")
            key, sep, value = text[offset:offset+size].partition(b"=")
            offset += size
            key = key.lower()
            need(bool(sep) and bool(key) and all(32 <= byte <= 126 for byte in key)
                and key not in fields, "discovery_identity_unproven")
            fields[key] = value
        need(fields.get(b"id") == identity.encode("ascii"), "discovery_identity_unproven")
        server = service.server.lower()
        need(server.endswith(".local.") and type(service.port) is int
            and 1 <= service.port <= 65535, "discovery_endpoint_invalid")
        addresses = self.records(server, 1)
        need(len(addresses) == 1, "discovery_partial_or_conflicting")
        address = ipaddress.IPv4Address(addresses[0].address)
        need(any(address in ipaddress.IPv4Network(network)
            for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")),
            "discovery_endpoint_invalid")
        # Any other allowlisted service advertising this same destination is
        # ambiguous, even if its TXT is incomplete. Never choose a winner.
        for other in DEVICES:
            if other == identity:
                continue
            for candidate in self.records(f"ewelink_{other}.{self.service_type}", 33):
                if candidate.port == service.port:
                    need(not any(record.address == addresses[0].address
                        for record in self.records(candidate.server, 1)),
                        "discovery_device_conflict")
        return (server, service.port, str(address), text)

    def incomplete_reason(self, identity):
        """Current cache structure only; no TXT values or endpoint leave here."""
        need(identity in DEVICES and not self.shared.done, "discovery_unavailable")
        name = f"ewelink_{identity}.{self.service_type}"
        services, texts = self.records(name, 33), self.records(name, 16)
        if not services and not texts:
            return "discovery_missing_srv_and_txt"
        if not services:
            return "discovery_missing_srv"
        if not texts:
            return "discovery_missing_txt"
        if len(services) != 1:
            return "discovery_conflicting_srv"
        if len(texts) != 1:
            return "discovery_conflicting_txt"
        server = services[0].server
        if not isinstance(server, str) or not server.lower().endswith(".local."):
            return "discovery_endpoint_invalid"
        addresses = self.records(server, 1)
        if not addresses:
            return "discovery_missing_address"
        if len(addresses) != 1:
            return "discovery_conflicting_address"
        return "discovery_partial_or_expired"

    async def resolve(self, identity):
        need(identity in DEVICES and not self.shared.done, "discovery_unavailable")
        # A complete, still-current exact cache binding needs no new discovery.
        try:
            token = self.binding(identity)
        except InvalidObservation as exc:
            if str(exc) != "discovery_partial_or_conflicting":
                raise
            reason = self.incomplete_reason(identity)
            need(reason in {"discovery_missing_srv_and_txt", "discovery_missing_srv",
                "discovery_missing_txt", "discovery_missing_address"}, reason)
        else:
            return {"address": token[2], "port": token[1]}, token
        # One bounded native PTR browse, followed by one exact resolution.
        # The browser is disposed before HTTP and never feeds switch state.
        async with asyncio.timeout(4):
            browser = AsyncServiceBrowser(self.shared, self.service_type,
                handlers=[lambda **_event: None])
            try:
                await asyncio.sleep(1.25)
            finally:
                await browser.async_cancel()
            expected = f"ewelink_{identity}.{self.service_type}"
            aliases = [record.alias for record in self.records(self.service_type, 12)
                if isinstance(record.alias, str) and record.alias.lower() == expected]
            need(bool(aliases), "discovery_ptr_missing")
            need(len(aliases) == 1, "discovery_ptr_conflicting")
            # DNS comparison is case-insensitive, but preserve the advertised
            # instance on the wire instead of synthesizing its spelling.
            info = AsyncServiceInfo(self.service_type, aliases[0])
            complete = await info.async_request(self.shared, 1500)
            if not complete:
                raise InvalidObservation(self.incomplete_reason(identity))
            token = self.binding(identity)
            need(info.server is not None and info.server.lower() == token[0]
                and info.port == token[1] and bytes(info.text) == token[3],
                "discovery_partial_or_conflicting")
            return {"address": token[2], "port": token[1]}, token

    def validate(self, identity, token):
        need(self.binding(identity) == token, "discovery_changed_or_expired")

    def validate_command_endpoint(self, identity, token):
        # A command may legitimately change encrypted TXT state. binding still
        # verifies exact identity, live records and destination collision rules.
        need(self.binding(identity)[:3] == token[:3], "discovery_changed_or_expired")


class RawListener(RecordUpdateListener):
    def __init__(self, receiver):
        self.receiver = receiver
        self.started_ms = current_time_millis()
        self.closed = False

    def async_update_records(self, zc, now, records):
        if self.closed or zc.done:
            return
        delay = (current_time_millis()-now)/1000
        if not 0 <= delay <= 2 or now < self.started_ms:
            return
        received_at = self.receiver.state.utcnow()-timedelta(seconds=delay)
        received_mono = self.receiver.state.monotonic()-delay
        for update in records:
            record = update.new
            # No ServiceInfo/cache lookup: TXT bytes and created clock come
            # directly from this packet's RecordUpdate before cache mutation.
            if not isinstance(record, DNSText) or record.created != now:
                continue
            name = record.name.lower()
            identity = next((d for d in self.receiver.state.channels
                if name == f"ewelink_{d}._ewelink._tcp.local."), None)
            if identity is None:
                continue
            if record.ttl <= 0:
                self.receiver.state.invalidate(identity, "device_goodbye")
                continue
            self.receiver.submit(identity, bytes(record.text), received_at, received_mono)

    def async_update_records_complete(self):
        pass


class Receiver:
    def __init__(self, state, store, create_task, discovery=None):
        self.state, self.store, self.create_task = state, store, create_task
        self.discovery = discovery
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.closed = False
        self.query_times = {}
        self.availability = {}
        self.storage_failed = False
        self.next_storage_recovery = 0.0

    def storage_failure(self, metadata):
        # A timed-out save may still finish on disk. Retain its high-water
        # conservatively, but never publish its unverified switch observations.
        self.state.highwater = deepcopy(metadata["devices"])
        self.storage_failed = True
        self.next_storage_recovery = self.state.monotonic() + 5
        self.state.healthy = False
        for device in self.state.channels:
            self.state.invalidate(device, "replay_store_unavailable")

    async def recover_storage(self):
        if (self.closed or not self.storage_failed
                or self.state.monotonic() < self.next_storage_recovery):
            return
        self.next_storage_recovery = self.state.monotonic() + 5
        try:
            persisted = await self.store.async_load()
            recovered = ObserverState(self.state.config, persisted,
                monotonic=self.state.monotonic, utcnow=self.state.utcnow)
            for identity, current in self.state.highwater.items():
                durable = recovered.highwater.setdefault(identity, deepcopy(current))
                durable["blocked"] = durable["blocked"] or current["blocked"]
                for source, mark in current["sources"].items():
                    prior = durable["sources"].get(source)
                    if prior is None or mark["sequence"] > prior["sequence"]:
                        durable["sources"][source] = deepcopy(mark)
                    elif mark["sequence"] == prior["sequence"] and mark["digest"] != prior["digest"]:
                        durable["blocked"] = True
            await self.store.async_save(recovered.metadata())
        except Exception:
            return
        if self.closed:
            return
        self.state.highwater = recovered.highwater
        self.state.boot_id = recovered.boot_id
        for identity in self.state.channels:
            self.state.invalidate(identity, "storage_recovered_waiting_report")
        self.state.healthy = True
        self.storage_failed = False

    def submit(self, identity, wire, received_at, received_mono):
        if self.closed:
            return
        if len(self.tasks) >= 32:
            self.state.invalidate(identity, "receiver_overflow")
            return
        task = self.create_task(self.receive(identity, wire, received_at, received_mono, revision=self.state.revisions[identity]))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _persist(self, identity, *, source, sequence, params, report_digest, received_at, received_mono, device_sequence=None, expected_revision=None):
        need(expected_revision is None or expected_revision == self.state.revisions[identity], "observation_invalidated")
        try:
            metadata, candidate, revision = self.state.stage(identity, source=source, sequence=sequence,
                params=params, report_digest=report_digest, received_at=received_at, received_mono=received_mono,
                device_sequence=device_sequence)
        except InvalidObservation:
            if self.state.highwater.get(identity, {}).get("blocked"):
                try:
                    await self.store.async_save(self.state.metadata())
                except Exception:
                    self.storage_failure(self.state.metadata())
            raise
        try:
            await self.store.async_save(metadata)
        except asyncio.CancelledError:
            self.storage_failure(metadata)
            raise
        except Exception:
            self.storage_failure(metadata)
            raise InvalidObservation("replay_store_unavailable") from None
        if not self.closed:
            self.state.commit(identity, metadata, candidate, revision)

    async def receive(self, identity, wire, received_at, received_mono, revision=None):
        async with self.lock:
            if self.storage_failed:
                await self.recover_storage()
            if (self.closed or not self.state.healthy
                    or (revision is not None and revision != self.state.revisions[identity])):
                return
            try:
                envelope = parse_txt(wire)
                need(envelope.get("id") == identity, "txt_identity_mismatch")
                params = decode(envelope, self.state.config["devices"][identity]["device_key"])
                await self._persist(identity, source="mdns", sequence=envelope.get("seq"), params=params,
                    report_digest=hashlib.sha256(wire).hexdigest(),
                    received_at=received_at, received_mono=received_mono)
                self.state.diagnose(identity, "mdns", "explicit_report_processed")
            except InvalidObservation as exc:
                self.state.diagnose(identity, "mdns", str(exc))
                # Missing/duplicate reports cannot renew an earlier receipt.
                # Never log the raw packet, decrypted state or private key.
                return
            except Exception:
                self.state.diagnose(identity, "mdns", "report_processing_failed")
                self.state.invalidate(identity, "report_processing_failed")

    async def query(self, identity, session):
        need(identity in self.state.channels, "device_not_allowed")
        need(not self.closed and len(self.tasks) < 32, "observer_unavailable")
        task = self.create_task(self._query(identity, session))
        self.tasks.add(task)
        try:
            return await task
        finally:
            self.tasks.discard(task)

    async def _query(self, identity, session):
        need(identity in self.state.channels, "device_not_allowed")
        device = self.state.config["devices"][identity]
        endpoint = device.get("endpoint")
        need(self.discovery is not None or endpoint is not None, "query_endpoint_not_qualified")
        async with self.lock:
            if self.storage_failed:
                await self.recover_storage()
            need(not self.closed and self.state.healthy, "observer_unavailable")
            now = self.state.monotonic()
            need(now-self.query_times.get(identity, float("-inf")) >= 5, "query_rate_limited")
            self.query_times[identity] = now
            self.availability[identity] = {"state": "unknown", "checked_at": self.state.utcnow().isoformat(),
                "source": "correlated_controller_query", "output_state": "Unknown"}
            query_revision = self.state.revisions[identity]
            previous = self.state.highwater.get(identity, {}).get("sources", {}).get("query", {}).get("sequence", 0)
            request_id = str(max(time.time_ns() // 1_000_000, previous + 1))
            payload = query_payload(identity, device["device_key"], request_id)
            try:
                if self.discovery is not None:
                    try:
                        discovered, token = await self.discovery.resolve(identity)
                        need(endpoint is None or (endpoint["address"] == discovered["address"]
                            and endpoint["port"] == discovered["port"]), "discovery_config_conflict")
                        self.discovery.validate(identity, token)
                        endpoint = discovered
                        self.state.diagnose(identity, "discovery", "endpoint_metadata_resolved")
                    except asyncio.CancelledError:
                        raise
                    except InvalidObservation as exc:
                        self.state.diagnose(identity, "discovery", str(exc))
                        raise
                    except Exception:
                        self.state.diagnose(identity, "discovery", "discovery_unproven")
                        raise
                # Fixed path, fixed empty plaintext, no redirect, no retry and
                # no caller-provided URL/command/params. Endpoint is HA-private.
                async with asyncio.timeout(5):
                    self.availability[identity] = {"state": "offline", "checked_at": self.state.utcnow().isoformat(),
                        "source": "controller_query_unanswered", "output_state": "Unknown"}
                    async with session.post(
                            f"http://{endpoint['address']}:{endpoint['port']}/zeroconf/getState",
                            json=payload, allow_redirects=False,
                            headers={"Connection": "close"}) as response:
                        need(response.status == 200, "query_http_unproven")
                        raw = await response.content.read(MAX_BYTES+1)
                        received_at, received_mono = self.state.utcnow(), self.state.monotonic()
                        need(len(raw) <= MAX_BYTES, "query_response_too_large")
                        envelope = json.loads(raw)
                        need(isinstance(envelope, dict) and type(envelope.get("error")) is int
                            and envelope["error"] == 0, "query_response_unproven")
                        need("deviceid" not in envelope or envelope["deviceid"] == identity, "query_identity_mismatch")
                        need(envelope.get("sequence") == request_id, "query_correlation_missing_or_mismatch")
                        if self.discovery is not None:
                            self.discovery.validate(identity, token)
                        self.availability[identity] = {"state": "online", "checked_at": received_at.isoformat(),
                            "source": "correlated_controller_query", "output_state": "Unknown"}
                        # ACK-only controllers can anchor a subsequent raw report;
                        # the acknowledgement itself never supplies output state.
                        if "data" not in envelope and "iv" not in envelope:
                            need("seq" in envelope, "query_ack_without_encrypted_state")
                            seq = envelope.get("seq")
                            need(type(seq) is int and seq >= 0, "query_revision_invalid")
                            prior = self.state.highwater.get(identity, {})
                            previous_mdns = prior.get("sources", {}).get("mdns")
                            if (not prior.get("blocked") and previous_mdns and seq >= previous_mdns["sequence"]
                                    and any(row["fresh"] for row in self.state.snapshot(identity)["channels"])):
                                return "query_controller_available"
                            metadata = self.state.metadata()
                            entry = metadata["devices"].setdefault(identity, {
                                "generation": device["generation"], "sources": {}, "blocked": True})
                            entry["blocked"] = True
                            entry["anchor"] = {"request_id": request_id, "device_sequence": seq,
                                "received_at": received_at.isoformat()}
                            self.state.invalidate(identity, "query_anchor_waiting_report")
                            try:
                                await self.store.async_save(metadata)
                            except BaseException:
                                self.storage_failure(metadata)
                                raise
                            self.state.highwater = deepcopy(metadata["devices"])
                            self.state.anchors[identity] = {"device_sequence": seq,
                                "received_at": received_at, "received_mono": received_mono}
                            return "query_anchor_waiting_report"
                        need("data" in envelope or "iv" in envelope, "query_ack_without_encrypted_state")
                        need("data" in envelope, "query_data_missing")
                        need("iv" in envelope, "query_iv_missing")
                        need(isinstance(envelope["data"], str) and isinstance(envelope["iv"], str),
                            "query_encrypted_fields_invalid")
                        params = decode(envelope, device["device_key"], require_flag=False)
                        # seq is a content revision and can remain unchanged.
                        # Only the exact new request echo renews query evidence.
                        device_sequence = str(envelope["seq"]) if "seq" in envelope else None
                        need(device_sequence is None or device_sequence.isdecimal(), "query_revision_invalid")
                        await self._persist(identity, source="query", sequence=request_id,
                            params=params, report_digest=digest(envelope),
                            received_at=received_at, received_mono=received_mono, device_sequence=device_sequence,
                            expected_revision=query_revision)
                self.state.diagnose(identity, "query", "explicit_report_processed")
                return "explicit_query_report_received"
            except asyncio.CancelledError:
                raise
            except InvalidObservation as exc:
                self.state.diagnose(identity, "query", str(exc))
                return "query_unproven"
            except Exception:
                self.state.diagnose(identity, "query", "query_unproven")
                return "query_unproven"

    async def stop(self):
        self.closed = True
        self.state.healthy = False
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
