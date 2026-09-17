"""Worker consumer of owner authority. No issuer and no authority from discovery."""
from __future__ import annotations

import uuid
from .execution import NativeExecutionError
from .recovery import digest


class RecoverySession:
    def __init__(self, canonical, mission_id, *, incarnation=None):
        self.canonical, self.mission_id = canonical, mission_id
        self.incarnation = incarnation or uuid.uuid4().hex
        self.proof, self.grant = None, None

    def consume(self, held, *, worker_revision):
        receipt = self.canonical.recovery(self.mission_id, "read", {})
        state = receipt.get("state") or {}
        if state.get("release"):
            return self.confirmed_release()
        grant = state.get("grant") or {}
        scope = grant.get("scope") or {}
        hold = scope.get("hold") or {}
        generation_matches = scope.get("generation") == held.get("generation")
        # Historical holds can have an empty generation. Preserve that exact
        # evidence; the owner grant and authenticated scope must agree on the
        # separate canonical dispatch generation before consuming authority.
        if held.get("generation") in (None, "") and hold.get("generation") in (None, ""):
            current = receipt.get("scope") or {}
            generation_matches = (bool(scope.get("generation")) and current.get("generation") == scope["generation"]
                                  and current.get("hold") == hold)
        if (scope.get("mission_id") != self.mission_id or not generation_matches
                or held.get("mission_id", self.mission_id) != self.mission_id
                or (hold.get("notification_identity") or hold.get("blocker_fingerprint")) != held.get("blocker_fingerprint")
                or (scope.get("runtime") or {}).get("worker_revision") != worker_revision):
            raise NativeExecutionError("native_resume_scope_unproven")
        payload = {"grant_id": grant.get("grant_id"), "incarnation": self.incarnation,
                   "request_id": "consume-" + digest([grant.get("grant_id"), self.incarnation])[:40]}
        try:
            acknowledgement = self.canonical.recovery(self.mission_id, "consume", payload)
        except NativeExecutionError as exc:
            if str(exc) != "native_transport_unavailable":
                raise
            # Read back the one consume, never allocate another process/claim.
            read = self.canonical.recovery(self.mission_id, "read", {})
            acknowledgement = {"lease": (read.get("state") or {}).get("lease"),
                               "grant": (read.get("state") or {}).get("grant")}
        lease = acknowledgement.get("lease") or {}
        if (acknowledgement.get("grant") != grant or lease.get("consume") != payload
                or lease.get("released") is not False or lease.get("grant_id") != grant.get("grant_id")
                or type(lease.get("epoch")) is not int or lease["epoch"] <= 0
                or not isinstance(lease.get("claim_id"), str) or not lease["claim_id"].startswith("HNC-")):
            raise NativeExecutionError("native_resume_receipt_invalid")
        self.grant = grant
        self.proof = {k: lease[k] for k in ("grant_id", "incarnation", "epoch", "claim_id")}
        self.check()
        return {"grant": grant, "lease": lease}

    def confirmed_release(self, expected=None):
        state = self.canonical.recovery(self.mission_id, "read", {}).get("state") or {}
        release, lease = state.get("release") or {}, state.get("lease") or {}
        metadata = self.canonical.mission(self.mission_id)["mission"]["metadata"]
        native = metadata.get("hermes_native_execution") or {}
        if (not release or (expected is not None and release != expected) or lease.get("released") is not True
                or release.get("proof") != {k:lease.get(k) for k in ("grant_id", "incarnation", "epoch", "claim_id")}
                or native.get("mission_id") != self.mission_id or native.get("worker_claim_id")
                or native.get("native_execution_id") != release.get("native_execution_id")
                or native.get("head_sha") != release.get("head_sha")
                or native.get("owner_notification_head") != release.get("head_sha")
                or native.get("execution_status") != "OWNER_DECISION_REQUIRED"):
            raise NativeExecutionError("native_recovery_release_unproven")
        return {"release": release, "lease": lease, "completed": True}

    def check(self):
        if not self.proof:
            raise NativeExecutionError("native_recovery_fence_required")
        receipt = self.canonical.recovery(self.mission_id, "check", {"proof": self.proof})
        lease = receipt.get("lease") or {}
        if receipt.get("grant") != self.grant or any(lease.get(k) != v for k,v in self.proof.items()):
            raise NativeExecutionError("native_recovery_fence_invalid")
        return receipt

    def perform(self, kind, intent, call, evidence, *, readback=None):
        self.check()
        metadata = self.canonical.mission(self.mission_id)["mission"]["metadata"]
        intent = {**intent, "candidate": metadata.get("review_packet") or {}}
        effect_id = "effect-" + digest([self.mission_id, kind, intent])[:48]
        payload = {"proof": self.proof, "effect_id": effect_id, "kind": kind, "intent": intent}
        reserved = self.canonical.recovery(self.mission_id, "reserve", payload)
        effect = reserved.get("effect") or {}
        if effect.get("effect_id") != effect_id or effect.get("intent") != intent:
            raise NativeExecutionError("native_recovery_reservation_invalid")
        if reserved.get("may_execute") is not True:
            if effect.get("state") == "confirmed" and readback is not None:
                result = readback()
                if evidence(result, intent) == (effect.get("receipt") or {}).get("evidence"):
                    return result
            raise NativeExecutionError("native_recovery_effect_requires_reconciliation")
        try:
            # Canonical epoch is not a provider fencing token. An intent remains
            # unresolved if interrupted here, blocking takeover or blind resend.
            self.check()
            self.canonical.recovery_effect_id = effect_id
            try:
                result = call()
            finally:
                self.canonical.recovery_effect_id = None
            receipt = evidence(result, intent)
            completed = self.canonical.recovery(self.mission_id, "finish", {
                "proof": self.proof, "effect_id": effect_id, "outcome": "confirmed", "evidence": receipt})
            if (completed.get("effect") or {}).get("receipt") != {"outcome": "confirmed", "evidence": receipt}:
                raise NativeExecutionError("native_recovery_completion_invalid")
            return result
        except BaseException:
            # No refund, resend, or presumed failure; durable prepared survives.
            raise
