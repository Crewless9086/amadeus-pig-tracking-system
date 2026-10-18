"""Offline cloud scope, credential and worker boundary tests (no providers)."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from modules.charlie import cloud_intake as cloud
from modules.charlie.native_runner import intake_service as worker

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
TOKEN = "a" * 64
REVISION = "b" * 40


def provider():
    return {"worker_service_id": cloud.WORKER_SERVICE, "worker_deploy_id": "dep-" + "c" * 20,
        "worker_revision": REVISION, "api_service_id": cloud.API_SERVICE, "api_deploy_id": "dep-" + "d" * 20,
        "api_revision": REVISION, "observed_at": NOW.isoformat(), "evidence_sha256": "e" * 64}


def policy():
    deps = [{"case_id": case, "generation": i+1, "evidence_digest": "e"*64,
        "evidence_refs_digest": "f"*64, "dependency_id": "dep"+str(i), "anchor_event_id": "event"+str(i),
        "anchor_cycle_id": "cycle"+str(i)} for i,case in enumerate(sorted(cloud.CASE_IDS))]
    scope = {"contract": cloud.intake.CONTRACT, "mission_id": cloud.MISSION_ID, "mission_identity_digest": "a"*64,
        "owner_user_id": "42", "owner_binding": "b"*64, "producer_revision": "c"*40,
        "dependencies": deps, "allowed_effects": list(cloud.intake._EFFECTS)}
    expiry = (NOW+timedelta(minutes=20)).isoformat()
    return {"policy_id": cloud.POLICY_ID, "capability": cloud.intake.CAPABILITY,
        "scope_json": scope, "authority_tier": "auto", "enabled": True, "expires_at": expiry,
        "max_actions": 2, "max_cost": 0, "rollback_required": True, "deterministic_gate_required": True,
        "metadata_json": {cloud.META_KEY: {"contract": cloud.CONTRACT, "epoch_id": "f"*32,
            "status": "enabled", "issued_at": NOW.isoformat(), "expires_at": expiry,
            "scope_sha256": cloud.intake.digest(scope), "provider": provider(),
            "worker_token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(), "worker_instance": None, "cycles": []}}}


class CloudAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"RENDER_GIT_COMMIT": REVISION, "RENDER_SERVICE_ID": cloud.API_SERVICE})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_exact_provider_attestation_and_distinct_producer_source(self):
        self.assertEqual(cloud._provider(provider(), NOW), provider())
        p = policy()
        self.assertEqual(cloud._authenticate(p, TOKEN, NOW)["provider"]["api_revision"], REVISION)
        self.assertEqual(p["scope_json"]["producer_revision"], "c"*40)

    def test_provider_source_service_clock_and_shape_refusals(self):
        for key,value in (("worker_service_id",cloud.API_SERVICE),("api_service_id",cloud.WORKER_SERVICE),
                          ("api_revision","a"*40),("worker_revision","short"),
                          ("observed_at",(NOW-timedelta(minutes=11)).isoformat()),
                          ("observed_at",(NOW+timedelta(seconds=1)).isoformat())):
            with self.subTest(key=key,value=value):
                p=provider();p[key]=value
                with self.assertRaises(cloud.CloudIntakeRefused): cloud._provider(p,NOW)
        p=provider();p["enable_builder"]=True
        with self.assertRaises(cloud.CloudIntakeRefused): cloud._provider(p,NOW)

    def test_epoch_bound_token_does_not_accept_gateway_or_old_secret(self):
        for token in ("", "b"*64, "Bearer "+TOKEN, "x"*129):
            with self.subTest(token_length=len(token)), self.assertRaises(cloud.CloudIntakeRefused):
                cloud._authenticate(policy(), token, NOW)

    def test_expiry_disabled_revoked_and_replaced_scope_refuse(self):
        for change in ("expiry","disabled","revoked","scope","api"):
            p=policy()
            if change=="expiry": p["expires_at"]=p["metadata_json"][cloud.META_KEY]["expires_at"]=NOW.isoformat()
            if change=="disabled": p["enabled"]=False
            if change=="revoked": p["metadata_json"][cloud.META_KEY]["status"]="revoked"
            if change=="scope": p["scope_json"]["dependencies"][0]["generation"]+=1
            if change=="api": p["metadata_json"][cloud.META_KEY]["provider"]["api_revision"]="e"*40
            with self.subTest(change=change), self.assertRaises(cloud.CloudIntakeRefused): cloud._authenticate(p,TOKEN,NOW)

    def test_fixed_scope_cannot_admit_third_case_or_model_spend(self):
        for change in ("case","count","cost","mission","rollback"):
            p=policy()
            if change=="case": p["scope_json"]["dependencies"][0]["case_id"]="OTHER"
            if change=="count": p["max_actions"]=3
            if change=="cost": p["max_cost"]=0.01
            if change=="mission": p["scope_json"]["mission_id"]="OTHER"
            if change=="rollback": p["rollback_required"]=False
            with self.subTest(change=change), self.assertRaises(cloud.CloudIntakeRefused): cloud._fixed_scope(p)

    def test_public_projection_has_no_credential_or_raw_prior_rows(self):
        p=policy();p["metadata_json"]["private_old_grant"]={"secret":"DO_NOT_EXPOSE"}
        raw=json.dumps(cloud._public(p,NOW))
        self.assertNotIn(TOKEN,raw);self.assertNotIn("worker_token_sha256",raw);self.assertNotIn("DO_NOT_EXPOSE",raw)

    def test_default_disabled_never_connects(self):
        connector=Mock()
        with patch.dict(os.environ,{"CORE_CLOUD_INTAKE_ENABLED":"false"}):
            with self.assertRaisesRegex(cloud.CloudIntakeRefused,"cloud_intake_disabled"):
                cloud.readiness(connect_factory=connector)
        connector.assert_not_called()

    def test_no_owner_principal_or_extra_effect_can_create(self):
        with self.assertRaises(cloud.CloudIntakeRefused): cloud.create_epoch({"sql":"DELETE"},actor="owner-admin:test")
        p={k:"a"*64 for k in ("policy_sha256","mission_sha256","created_sha256","scope_sha256","worker_token_sha256")}
        p.update(duration_seconds=1200,provider=provider())
        with self.assertRaisesRegex(cloud.CloudIntakeRefused,"owner_principal_required"):
            cloud.create_epoch(p,actor="service:worker")
        for n in (True,0,1201):
            p["duration_seconds"]=n
            with self.subTest(n=n),self.assertRaisesRegex(cloud.CloudIntakeRefused,"epoch_duration_invalid"):
                cloud.create_epoch(p,actor="owner-admin:test")


class FakeStop:
    def __init__(self, maximum=2): self.maximum=maximum;self.waits=0
    def is_set(self): return False
    def wait(self, delay): self.waits+=1;return self.waits>=self.maximum


class FakeClient:
    def __init__(self, active=True): self.calls=[];self.active=active;self.fail=False
    def request(self,path,payload=None):
        self.calls.append((path,payload))
        if path=="/current":
            return {"contract":worker.CONTRACT,"epoch_id":"f"*32,"expires_at":(NOW+timedelta(minutes=20)).isoformat(),
                    "provider":provider(),"active":self.active}
        if self.fail: raise TimeoutError("secret response must never be printed")
        return {"contract":worker.CONTRACT,"epoch_id":payload["epoch_id"],"request_id":payload["request_id"],"success":True}


class ReceiptWorkerTests(unittest.TestCase):
    def run_worker(self,client,stop=None,clock=None):
        reports=[]
        code=worker.run_worker(environ={"CORE_NATIVE_RUNNER_MODE":"receipt_only",
            "RENDER_SERVICE_ID":cloud.WORKER_SERVICE,"RENDER_GIT_COMMIT":REVISION},client=client,
            clock=clock or (lambda:NOW),stop=stop or FakeStop(),report=reports.append)
        return code,reports

    def test_two_autonomous_cycles_keep_instance_and_distinct_requests(self):
        client=FakeClient();code,reports=self.run_worker(client)
        writes=[p for path,p in client.calls if path=="/cycles"]
        self.assertEqual(code,0);self.assertEqual(len(writes),2)
        self.assertEqual(writes[0]["worker_instance"],writes[1]["worker_instance"])
        self.assertNotEqual(writes[0]["request_id"],writes[1]["request_id"])
        self.assertFalse(reports[0]["model_initialized"])

    def test_pre_epoch_bootstrap_waits_then_accepts_fresh_owner_epoch(self):
        client=FakeClient();real=client.request;count=[0]
        def request(path,payload=None):
            count[0]+=1
            if count[0]==1:
                client.calls.append((path,payload))
                return {"contract":worker.CONTRACT,"status":"awaiting_epoch","active":False}
            return real(path,payload)
        client.request=request
        code,reports=self.run_worker(client,stop=FakeStop(3))
        self.assertEqual(code,0)
        self.assertEqual(sum(path=="/cycles" for path,_ in client.calls),2)
        self.assertTrue(any(r["status"]=="receipt_worker_awaiting_epoch" for r in reports))

    def test_disabled_mode_polls_without_cycle(self):
        client=FakeClient(active=False);self.run_worker(client)
        self.assertTrue(all(path=="/current" for path,_ in client.calls))

    def test_expired_grant_does_not_submit(self):
        client=FakeClient();code,reports=self.run_worker(client,clock=lambda:NOW+timedelta(hours=1))
        self.assertEqual(code,0);self.assertEqual(len(client.calls),1)
        self.assertEqual(reports[-2]["status"],"receipt_epoch_expired")

    def test_revocation_stops_previously_active_worker(self):
        client=FakeClient();original=client.request
        def request(path,payload=None):
            if len(client.calls)>=2: client.active=False
            return original(path,payload)
        client.request=request
        code,reports=self.run_worker(client,stop=FakeStop(99))
        self.assertEqual(code,0);self.assertEqual(sum(p=="/cycles" for p,_ in client.calls),1)
        self.assertEqual(reports[-1]["status"],"receipt_worker_stopped")

    def test_ambiguous_post_is_not_retried_or_logged(self):
        client=FakeClient();client.fail=True
        code,reports=self.run_worker(client)
        self.assertEqual(code,0);self.assertEqual(len(client.calls),2)
        self.assertNotIn("secret response",json.dumps(reports))

    def test_worker_revision_mismatch_fails_before_cycle(self):
        client=FakeClient();real=client.request
        def changed(path,payload=None):
            result=real(path,payload);result["provider"]["worker_revision"]="d"*40;return result
        client.request=changed
        self.assertEqual(self.run_worker(client)[0],0);self.assertEqual(len(client.calls),1)

    def test_bootstrap_receipt_mode_never_prepares_builder(self):
        path=Path(__file__).parents[1]/"scripts/charlie_render_native_runner.py"
        spec=importlib.util.spec_from_file_location("receipt_bootstrap_test",path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.dict(os.environ,{"CORE_NATIVE_RUNNER_MODE":"receipt_only"}), \
             patch.object(module,"prepare_repository",side_effect=AssertionError("builder repo")), \
             patch.object(module,"prepare_hermes_profile",side_effect=AssertionError("builder profile")), \
             patch.object(worker,"main",return_value=0) as run:
            with self.assertRaises(SystemExit) as raised: module.main()
            self.assertEqual(raised.exception.code,0);run.assert_called_once()

    def test_http_client_refuses_redirect_and_oversized_body(self):
        with self.assertRaises(worker.IntakeWorkerRefused): worker.NoRedirect().redirect_request(None,None,None,None,None,None)
        response=Mock(status=200);response.read.return_value=b"x"*65537
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with self.assertRaises(worker.IntakeWorkerRefused): worker.ReceiptClient(TOKEN,opener=opener).request("/current")
        with self.assertRaises(worker.IntakeWorkerRefused): worker.ReceiptClient(TOKEN,opener=opener).request("/executive/cycle")


class CloudRouteTests(unittest.TestCase):
    def setUp(self):
        from flask import Flask
        from modules.auth.owner_access import configure_owner_access, set_owner_session
        from modules.charlie.routes import charlie_bp
        self.env=patch.dict(os.environ,{"OWNER_ACCESS_ENABLED":"1","OWNER_ACCESS_ALLOW_LOCAL_DEV":"0",
            "OWNER_ADMIN_TOKEN":"x"*64,"OWNER_READ_TOKEN":"y"*64,"OWNER_SESSION_SECRET":"z"*64})
        self.env.start();self.addCleanup(self.env.stop)
        self.app=Flask(__name__);configure_owner_access(self.app)
        self.app.register_blueprint(charlie_bp,url_prefix="/api")
        @self.app.route("/fixture-login/<role>")
        def login(role):set_owner_session(role);return "ok"
        self.client=self.app.test_client()
        self.base="/api/charlie/core/manager-intake/cloud"

    def test_worker_bearer_and_read_role_cannot_commission_or_revoke(self):
        with patch.object(cloud,"create_epoch") as called:
            for role in (None,"read"):
                if role:self.client.get("/fixture-login/"+role,base_url="https://localhost")
                response=self.client.post(self.base+"/epochs",json={},headers={"Authorization":"Bearer "+TOKEN},base_url="https://localhost")
                self.assertEqual(response.status_code,403)
            called.assert_not_called()

    def test_strict_owner_route_uses_server_principal_and_bounds_payload(self):
        self.client.get("/fixture-login/admin",base_url="https://localhost")
        with patch.object(cloud,"create_epoch",return_value={"contract":cloud.CONTRACT}) as create:
            response=self.client.post(self.base+"/epochs",json={},base_url="https://localhost")
            self.assertEqual(response.status_code,200)
            self.assertTrue(create.call_args.kwargs["actor"].startswith("owner-admin:"))
            response=self.client.post(self.base+"/epochs",json={"huge":"x"*17000},base_url="https://localhost")
            self.assertEqual(response.status_code,413);self.assertEqual(create.call_count,1)

    def test_readback_route_remains_owner_only_and_does_not_run_cycle(self):
        with patch.object(cloud,"evidence",return_value={"contract":cloud.CONTRACT}) as read:
            url=self.base+"/epochs/"+"f"*32+"/evidence"
            self.assertEqual(self.client.get(url,base_url="https://localhost").status_code,403)
            self.client.get("/fixture-login/admin",base_url="https://localhost")
            self.assertEqual(self.client.get(url,base_url="https://localhost").status_code,200)
            read.assert_called_once_with("f"*32)


if __name__ == "__main__":
    unittest.main()
