"""Exact PR1404 pending-registration succession to ROOTLINE PR1405.

A separate maintainer entry. Never upgrades, invalidates or issues an admission.
Source pins and synthetic qualification confer no authority to apply.
"""
from copy import deepcopy
from pathlib import Path
import re
import json
import subprocess
from scripts import reconcile_oom_desktop_candidate as ordinary
from modules.charlie.mission_control import (
    build_mission_control_event, canonical_event_equal, apply_event_to_projection,
    validate_mission_control_event)

canonical, digest = ordinary.canonical, ordinary.digest
_require, _fields, _sha, _time, _load = (ordinary._require, ordinary._fields,
    ordinary._sha, ordinary._time, ordinary._load)
ReconciliationError = ordinary.ReconciliationError
ROOT = Path(__file__).resolve().parents[1]
VERSION = 'rootline_pending_registration_successor_v1'
DECISION = 'succeed_exact_pending_pr1404_registration_with_rootline_pr1405'
MISSION_ID, PARENT_ID, TASK_ID = ordinary.MISSION_ID, ordinary.PARENT_ID, ordinary.TASK_ID
PREDECESSOR_TREE = '0947c8418c39c6d76e812d3d1f8e818270f1560b'
OLD_ADMITTED_HEAD = 'b6843773547c62d7a8b8b641af3fe0e66c87c062'
OLD_ADMITTED_BASE = '549f3b7bb20bcc4598ee8edc5bf537a0e662e407'
BASE = '18de462e8463b44b289b29eda3693606d9b1e43a'
CANDIDATE_PR = 1405
HEAD = 'cb9f89442a472bff3711740cb11d823777104679'
TREE = '71a6ab72ae511110c2580cbb6eb679228bc7d81c'
APPROVED_RUNTIME_HEAD = 'cb9f89442a472bff3711740cb11d823777104679'
QUALIFICATION_TEST_PATHS = []
BRANCH = 'codex/rootline-resume-20261025'
PREDECESSOR_PR = 1404
PREDECESSOR_BASE = '18de462e8463b44b289b29eda3693606d9b1e43a'
PREDECESSOR_HEAD = '70aecb0259b90d85367ecab08e4134d805e99a71'
PREDECESSOR_BRANCH = 'codex/core-builder-contract-20261022'
PATHS = ['.github/workflows/oom-sakkie-audit-rails.yml', 'docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md', 'modules/oom_sakkie/rootline_daily_presentation.py', 'modules/oom_sakkie/rootline_material.py', 'modules/oom_sakkie/rootline_reassessment_lifecycle.py', 'modules/telemetry/rootline_execution_runtime.py', 'modules/telemetry/rootline_irrigation_execution_store.py', 'modules/telemetry/rootline_irrigation_history.py', 'modules/telemetry/rootline_irrigation_lifecycle.py', 'modules/telemetry/rootline_managed_devices_runtime.py', 'modules/telemetry/rootline_specialist_result.py', 'modules/telemetry/rootline_water_energy_plan.py', 'tests/test_oom_sakkie_owner_response_composer.py', 'tests/test_oom_sakkie_rootline_daily_presentation.py', 'tests/test_rootline_irrigation_execution_history_postgres.py', 'tests/test_rootline_managed_evidence_history_postgres.py', 'tests/test_rootline_managed_recovery_planning.py', 'tests/test_rootline_shutdown_preservation.py']
PREDECESSOR_PATHS = ['docs/06-operations/CORE_CLOUD_ENGINEERING_TRIAL.md', 'modules/charlie/native_runner/engineering_service.py', 'modules/charlie/native_runner/execution.py', 'tests/test_charlie_cloud_engineering_service.py', 'tests/test_charlie_native_runner.py']
WEB_SERVICE = 'srv-d6sijjkhg0os73f7regg'
WEB_BASELINE = '18de462e8463b44b289b29eda3693606d9b1e43a'
WEB_ROLLBACK = '18de462e8463b44b289b29eda3693606d9b1e43a'

HELPERS = ('modules/charlie/mission_store.py', 'modules/charlie/mission_control.py',
    'scripts/reconcile_oom_desktop_candidate.py', 'scripts/render_oom_desktop_registration_sql.py')
MAINTAINER_PATHS = ordinary.MAINTAINER_PATHS | {
    'scripts/reconcile_rootline_pending_registration.py',
    'tests/test_rootline_pending_registration.py', 'tests/test_rootline_pending_registration_sql.py'}
REMOVED_EFFECTS = {'core_cloud_engineering_worker_release:srv-dacofeoae00c73813eug:' + PREDECESSOR_HEAD}
REMOVED_FORBIDDEN_EFFECTS = {'service_deploy_outside:srv-d6sijjkhg0os73f7regg,srv-dacofeoae00c73813eug'}
ADDED_FORBIDDEN_EFFECTS = {'service_deploy_outside:' + WEB_SERVICE,
    'core_cloud_engineering_worker_deployment', 'core_cloud_engineering_worker_activation',
    'core_cloud_engineering_trial_activation', 'core_cloud_receipt_trial_activation'}
REQUIRED_TESTS = ordinary.REQUIRED_TESTS


def _acceptance():
    # The unmodified ordinary helper and immutable prior history retain the old
    # clauses. They do not remain active worker/trial authority in this contract.
    retired = ('No scheduler deployment, webhook cutover',
        'Release only the protected merge whose application tree',
        'Require an independently authenticated attributable owner instruction',
        'For stopped-image validation alone,', 'Cloud receipt-only source:',
        'Cloud current-producer source:', 'Cloud engineering infrastructure is separate')
    inherited = set(ordinary.REQUIRED_ACCEPTANCE)
    for prefix in retired:
        found = {v for v in inherited if v.startswith(prefix)}
        _require(len(found) == 1, 'inherited_acceptance_changed')
        inherited -= found
    trial = 'one unused receipt-only recovery trial remains separately bounded and explicitly approved.'
    inherited = {v.replace(trial, 'all historical CORE trials remain parked and confer no authority here.') for v in inherited}
    return inherited | {
        f'Release only exact ROOTLINE PR{CANDIDATE_PR} head {HEAD}, tree {TREE}, base {BASE}, after independently approved registration, fresh protected admission and required checks. Source pins, publication and tests confer no merge, deployment, farm or activation authority.',
        f'Only existing web service {WEB_SERVICE} is in proposed deployment scope, with exact rollback {WEB_ROLLBACK}. Preserve existing ROOTLINE scheduler and configuration. No CORE worker deployment/resume/activation/trial, token rotation, spending, scheduler deployment/manual trigger, migration or configuration change. CORE remains parked and suspended; historical CORE approvals cannot authorize this release.',
        'Require independently authenticated fresh owner approval of this exact pending PR1404-to-ROOTLINE succession, manifest, three-write shape and web-only scope. Current publication/test approval is insufficient. Preserve the invalidated PR1403 admission byte-for-byte, exact parent and all earlier registration/correction/attempt history. Issue no admission and do not replay the historical five-write transition.',
        'Require exact current pending registration history, manifest and approval digests, child and parent preimages, prior correction and invalidated signed receipt. Refuse unknown/mismatched history, newer correction, active execution, another admission or changed source. Append one genuine owner correction, one conditional child binding/projection update and one immutable history event atomically; verify semantic readback and zero-write replay. Ordinary valid-predecessor and canonical invalidation rules remain unchanged.',
        'Existing B/C and borehole enabled flags remain unchanged; grant no new ON, borehole or fertilizer authority. Managed-device recovery including borehole is affected by this web candidate. Borehole enabled and Needs Data/storage unavailable do not prove commissioning, pumping or authority. Preserve shutdown/recovery safety and all existing interlocks; do not change flags proactively.',
        'Retain plan22 and both Oct20 B/C jobs as independent historical work. Recorded recovery OFF proves only that historical shutdown observation; runtime/remainder and current OFF remain unproven. Preserve restart_after_pre_on_claim containment, do not count watering or clear C through a B-only cancellation path, and do not claim this release resolves those holds.',
        'Before an owner outcome require exact loaded web revision and a genuine natural B/C scheduler, plan, command, authoritative readback, runtime evidence and follow-up chain, replay containment and later independent continuity. Missing gateway timing, runtime/remainder, current state or authority remains held. Passing helper tests, admission, deploy or notification delivery never proves physical irrigation. NO BUSINESS OUTCOME until operational acceptance.'}


REQUIRED_ACCEPTANCE = _acceptance()


def prepare_pending_succession(manifest_bytes, approval_bytes, *, expected_manifest_sha256,
                               expected_approval_sha256, now=None):
    """Validate the exact pending path without fabricating valid admission state."""
    now = now or ordinary._now()
    m = _fields(_load(manifest_bytes, expected_manifest_sha256, 'manifest'), {
        'version', 'mission_id', 'parent_mission_id', 'candidate', 'generation', 'desktop',
        'expected_child_record', 'expected_child_sha256', 'expected_parent_record', 'expected_parent_sha256',
        'expected_correction', 'expected_registration', 'contract', 'implementation', 'idempotency_key', 'expires_at'}, 'manifest_fields')
    a = _fields(_load(approval_bytes, expected_approval_sha256, 'approval'), {
        'version', 'decision', 'approval_id', 'manifest_sha256', 'owner_principal', 'desktop_task_id',
        'source', 'evidence_ref', 'instruction_text', 'issued_at', 'expires_at'}, 'approval_fields')
    _require(m['version'] == a['version'] == VERSION and a['decision'] == DECISION
        and m['mission_id'] == MISSION_ID and m['parent_mission_id'] == PARENT_ID
        and a['manifest_sha256'] == expected_manifest_sha256, 'scope_or_approval_mismatch')
    for key in ('approval_id', 'owner_principal', 'evidence_ref', 'instruction_text'):
        _require(isinstance(a[key], str) and a[key].strip() == a[key] and 1 <= len(a[key]) <= 2000, 'approval_identity_missing')
    _require(len(a['owner_principal']) <= 180 and len(a['evidence_ref']) <= 500, 'approval_identity_too_long')
    issued, expires = _time(a['issued_at']), _time(a['expires_at'])
    _require(issued <= now < expires and expires == _time(m['expires_at'])
        and 0 < (expires-issued).total_seconds() <= 86400, 'approval_not_current')
    source = _fields(a['source'], {'kind','task_id','request_text','answer_text','transcript_sha256','observed_at','source_message_id'}, 'approval_source_fields')
    _require(source['kind'] == 'current_conversation_transcript' and source['task_id'] == TASK_ID
        and source['source_message_id'] is None
        and all(isinstance(source[k], str) and source[k].strip() for k in ('request_text','answer_text'))
        and digest(canonical({k:source[k] for k in ('task_id','request_text','answer_text')})) == source['transcript_sha256']
        and _time(source['observed_at']) <= issued, 'approval_source_invalid')
    _require(m['desktop'] == {'task_id':TASK_ID,'principal':'codex_desktop:'+TASK_ID,'transport':'codex_desktop'}
        and a['desktop_task_id'] == TASK_ID, 'desktop_identity_invalid')
    for key in ('generation','idempotency_key'):
        _require(isinstance(m[key], str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{7,159}',m[key]), key+'_invalid')
    c = _fields(m['candidate'], {'pr_number','branch','base_sha','head_sha','tree_sha','diff_sha256','changed_files'}, 'candidate_fields')
    _require(type(c['pr_number']) is int and c['pr_number'] == CANDIDATE_PR and c['branch'] == BRANCH
        and c['base_sha'] == BASE and c['head_sha'] == HEAD and c['tree_sha'] == TREE
        and _sha(c['diff_sha256']) and c['changed_files'] == PATHS, 'candidate_identity_changed')
    impl = _fields(m['implementation'], {'base_revision','adapter_sha256','helper_files'}, 'implementation_fields')
    _require(impl['base_revision'] == BASE and _sha(impl['adapter_sha256'])
        and set(impl['helper_files']) == set(HELPERS) and all(_sha(v) for v in impl['helper_files'].values()), 'implementation_pins_invalid')
    for label, mid in (('child',MISSION_ID),('parent',PARENT_ID)):
        row=m['expected_'+label+'_record']
        _require(isinstance(row,dict) and row.get('mission_id')==mid and row.get('status')=='in_progress'
            and isinstance(row.get('metadata_json'),dict) and digest(canonical(row))==m['expected_'+label+'_sha256'], 'expected_'+label+'_record_invalid')
    md=m['expected_child_record']['metadata_json']
    _require(not md.get('execution_lease') and not any((md.get(k) or {}).get('status')=='valid'
        for k in ('dispatch_authorization','hermes_native_execution')), 'active_execution_conflict')
    registration=_fields(m['expected_registration'], {'event_id','metadata','recorded_by'}, 'registration_fields')
    h=_fields(registration['metadata'], {'version','manifest','approval','manifest_sha256','approval_sha256',
        'previous_record','parent_record','correction','invalidated_admission','bindings'}, 'registration_history_fields')
    pm, pa, bindings=h['manifest'],h['approval'],h['bindings']
    _require(isinstance(pm,dict) and isinstance(pa,dict) and isinstance(bindings,dict)
        and h['version']==ordinary.VERSION and pm.get('version')==pa.get('version')==ordinary.VERSION
        and digest(canonical(pm))==h['manifest_sha256'] and digest(canonical(pa))==h['approval_sha256']
        and pa.get('manifest_sha256')==h['manifest_sha256'] and pa.get('decision')==ordinary.DECISION
        and pa.get('owner_principal')==registration['recorded_by']
        and registration['event_id']=='OOM-DESKTOP-REBIND-'+h['manifest_sha256'].upper(), 'registration_history_invalid')
    pc=pm.get('candidate') or {}; contract=pm.get('contract') or {}; family=bindings.get('mission_family') or {}
    _require(pm.get('mission_id')==MISSION_ID and pm.get('parent_mission_id')==PARENT_ID
        and type(pc.get('pr_number')) is int and pc['pr_number']==PREDECESSOR_PR
        and pc.get('head_sha')==PREDECESSOR_HEAD and pc.get('base_sha')==PREDECESSOR_BASE
        and pc.get('branch')==PREDECESSOR_BRANCH and pc.get('changed_files')==PREDECESSOR_PATHS
        and pc.get('tree_sha')==PREDECESSOR_TREE and _sha(pc.get('diff_sha256'))
        and contract.get('generation')==pm.get('generation')==family.get('generation')
        and contract.get('base_sha')==PREDECESSOR_BASE and contract.get('branch')==PREDECESSOR_BRANCH
        and contract.get('allowed_files')==PREDECESSOR_PATHS
        and family.get('root_mission_id')==family.get('parent_mission_id')==PARENT_ID, 'pending_predecessor_binding_invalid')
    expected_bindings={'review_packet':{'pr_number':PREDECESSOR_PR,'branch_name':PREDECESSOR_BRANCH,
        'candidate_revision':PREDECESSOR_HEAD,'candidate_tree':pc['tree_sha'],'candidate_diff_sha256':pc['diff_sha256'],
        'changed_files':PREDECESSOR_PATHS},'mission_admission_contract':contract,'mission_family':family,
        'external_supervisor':pm.get('desktop'),'desktop_candidate_reconciliation':{'version':ordinary.VERSION,
        'event_id':registration['event_id'],'manifest_sha256':h['manifest_sha256'],'approval_sha256':h['approval_sha256']}}
    _require(bindings==expected_bindings and all(md.get(k)==v for k,v in bindings.items())
        and h['previous_record']==pm.get('expected_child_record')
        and h['parent_record']==pm.get('expected_parent_record')==m['expected_parent_record']
        and digest(canonical(h['previous_record']))==pm.get('expected_child_sha256')
        and digest(canonical(h['parent_record']))==pm.get('expected_parent_sha256'), 'pending_history_binding_invalid')
    admission=md.get('mission_admission') or {}; old=(h['previous_record'].get('metadata_json') or {}).get('mission_admission') or {}
    correction=_fields(m['expected_correction'], {'event_id','metadata','recorded_by'}, 'correction_fields')
    prior_event=h['correction']
    _require(validate_mission_control_event(prior_event)[0] and prior_event.get('mission_id')==MISSION_ID
        and prior_event.get('event_type')=='owner_correction_recorded'
        and correction=={'event_id':prior_event['event_id'],'metadata':prior_event,'recorded_by':registration['recorded_by']}
        and prior_event.get('recorded_by')==registration['recorded_by'], 'predecessor_correction_invalid')
    correction_digest=digest(json.dumps({k:v for k,v in prior_event.items() if k!='recorded_at'}, sort_keys=True, separators=(',', ':')).encode())
    expected_invalidated={**old,'status':'invalidated','invalidated_by_correction_event_id':prior_event['event_id'],
        'correction_digest':correction_digest,'replacement_generation':pm['generation']}
    _require(old.get('status')=='valid' and old.get('mission_id')==MISSION_ID and old.get('root_mission_id')==PARENT_ID
        and old.get('head_sha')==OLD_ADMITTED_HEAD and old.get('base_sha')==OLD_ADMITTED_BASE
        and isinstance(old.get('signed_receipt'),dict) and bool(old['signed_receipt'])
        and old.get('generation') and admission==h['invalidated_admission']==expected_invalidated
        and m['generation'] not in {old['generation'],pm['generation']}, 'pending_invalidation_proof_invalid')
    signed=old['signed_receipt']
    _require(signed.get('mission')=={'mission_id':MISSION_ID,'root_mission_id':PARENT_ID,'generation':old['generation']}
        and (signed.get('candidate') or {}).get('head_sha')==OLD_ADMITTED_HEAD
        and (signed.get('candidate') or {}).get('base_sha')==OLD_ADMITTED_BASE
        and all(signed.get(k)==old.get(k) and _sha(old.get(k)) for k in ('content_sha256','authority_key_sha256'))
        and signed.get('receipt_id')==old.get('receipt_id')
        and (signed.get('owner_instruction_chain') or {}).get('latest_correction_digest')==old.get('latest_correction_digest')
        and (signed.get('collision_snapshot') or {}).get('snapshot_sha256')==old.get('collision_snapshot_sha256'), 'stored_receipt_binding_invalid')
    _require(m['idempotency_key']!=pm.get('idempotency_key') and a['approval_id']!=pa.get('approval_id')
        and issued>_time(prior_event['recorded_at']) and _time(source['observed_at'])>_time(prior_event['recorded_at']), 'fresh_succession_required')
    proposed=_fields(m['contract'], {'generation','branch','base_sha','allowed_files','forbidden_files',
        'allowed_effects','forbidden_effects','required_tests','operational_acceptance'}, 'contract_fields')
    _require(proposed['generation']==m['generation'] and proposed['branch']==BRANCH and proposed['base_sha']==BASE
        and proposed['allowed_files']==PATHS, 'contract_identity_changed')
    for key in ('allowed_files','forbidden_files','allowed_effects','forbidden_effects','required_tests','operational_acceptance'):
        values=proposed[key]
        _require(isinstance(values,list) and values and len(values)<=(108 if key=='operational_acceptance' else 100)
            and all(isinstance(v,str) and 0<len(v)<=2000 for v in values) and len(set(values))==len(values), 'contract_lists_invalid')
    _require(REMOVED_EFFECTS<=set(contract['allowed_effects']) and REMOVED_FORBIDDEN_EFFECTS<=set(contract['forbidden_effects'])
        and set(proposed['allowed_effects'])==set(contract['allowed_effects'])-REMOVED_EFFECTS
        and set(proposed['forbidden_effects'])==set(contract['forbidden_effects'])-REMOVED_FORBIDDEN_EFFECTS|ADDED_FORBIDDEN_EFFECTS
        and set(proposed['forbidden_files'])==set(contract['forbidden_files'])
        and REQUIRED_TESTS|set(contract['required_tests'])<=set(proposed['required_tests'])
        and set(proposed['operational_acceptance'])==REQUIRED_ACCEPTANCE
        and not set(proposed['allowed_effects'])&set(proposed['forbidden_effects']), 'approved_scope_delta_changed')
    return {'manifest':m,'approval':a,'manifest_sha256':expected_manifest_sha256,'approval_sha256':expected_approval_sha256,
        'event_id':'ROOTLINE-PENDING-SUCCESSION-'+expected_manifest_sha256.upper()}


def verify_source_and_candidate(plan):
    def git(*args):
        return subprocess.check_output(['git','--no-optional-locks',*args],cwd=ROOT)
    _require(git('rev-parse','origin/main').decode().strip()==BASE, 'protected_main_changed')
    _require(set(git('diff','--name-only',BASE,'--').decode().splitlines())<=MAINTAINER_PATHS, 'trusted_checkout_changed')
    _require(set(git('ls-files','--others','--exclude-standard').decode().splitlines())<=MAINTAINER_PATHS, 'untracked_trusted_dependency')
    m=plan['manifest']
    _require(digest(Path(__file__).read_bytes())==m['implementation']['adapter_sha256'], 'adapter_source_changed')
    for path,sha in m['implementation']['helper_files'].items():
        _require(digest((ROOT/path).read_bytes())==sha, 'helper_source_changed')
    _require(git('rev-parse',HEAD+'^{tree}').decode().strip()==TREE, 'candidate_tree_changed')
    paths=sorted(git('diff','--name-only',BASE,HEAD,'--').decode().splitlines())
    _require(paths==PATHS, 'candidate_paths_changed')
    patch=git('diff','--no-ext-diff','--no-textconv','--binary','--full-index',BASE,HEAD,'--')
    from modules.charlie.mission_admission import canonical_candidate_diff
    _require(canonical_candidate_diff(paths,patch)==m['candidate']['diff_sha256'], 'candidate_diff_changed')


def _bindings(plan):
    m=plan['manifest']; c=m['candidate']
    family={**m['expected_child_record']['metadata_json']['mission_family'],'generation':m['generation']}
    return {'review_packet':{'pr_number':CANDIDATE_PR,'branch_name':BRANCH,'candidate_revision':HEAD,
        'candidate_tree':TREE,'candidate_diff_sha256':c['diff_sha256'],'changed_files':PATHS},
        'mission_admission_contract':m['contract'],'mission_family':family,'external_supervisor':m['desktop'],
        'desktop_candidate_reconciliation':{'version':VERSION,'event_id':plan['event_id'],
            'manifest_sha256':plan['manifest_sha256'],'approval_sha256':plan['approval_sha256']}}


def _signed_receipt_matches(current):
    signed=current.get('signed_receipt') or {}
    return isinstance(signed,dict) and signed.get('mission')=={k:current.get(k) for k in ('mission_id','root_mission_id','generation')} and all(
        (signed.get('candidate') or {}).get(k)==current.get(k) and _sha(current.get(k),40) for k in ('head_sha','base_sha')) and all(
        signed.get(k)==current.get(k) and _sha(current.get(k)) for k in ('content_sha256','authority_key_sha256')) and signed.get('receipt_id')==current.get('receipt_id') and isinstance(current.get('receipt_id'),str)


def _correction(plan, *, now=None):
    m,a=plan['manifest'],plan['approval']
    payload={'event_type':'owner_correction_recorded','summary':a['instruction_text'],
        'corrects_event_id':m['expected_correction']['event_id'],'idempotency_key':m['idempotency_key']+':owner',
        'current_worker':m['desktop']['principal'],'evidence_refs':[a['evidence_ref'],'sha256:'+plan['manifest_sha256'],'sha256:'+plan['approval_sha256']]}
    return build_mission_control_event(MISSION_ID,payload,recorded_by=a['owner_principal'],now=now)


def _later_admission(current, plan):
    m=plan['manifest']
    return isinstance(current,dict) and current.get('status') in {'valid','consumed','revoked','invalidated'} and all(
        current.get(k)==v for k,v in {'mission_id':MISSION_ID,'root_mission_id':PARENT_ID,
        'generation':m['generation'],'base_sha':BASE,'head_sha':HEAD}.items()) and _signed_receipt_matches(current)


OWNER_HOLD_QUERY = "select h.event_id from public.charlie_owner_execution_hold_events h where h.mission_id in (%s,%s) and h.event_type='hold_created' and not exists (select 1 from public.charlie_owner_execution_hold_events r where r.event_type='hold_released' and r.release_of_event_id=h.event_id) limit 1"


def reconcile_pending_succession(manifest_bytes, approval_bytes, *, expected_manifest_sha256,
        expected_approval_sha256, authenticated_owner_principal='', authenticated_desktop_principal='',
        dry_run=True, database_url=None, connect_factory=None):
    plan=prepare_pending_succession(manifest_bytes,approval_bytes,expected_manifest_sha256=expected_manifest_sha256,
        expected_approval_sha256=expected_approval_sha256)
    if dry_run:
        return {'status':'prepared_pending_succession','writes':0,**plan}
    m,a=plan['manifest'],plan['approval']
    _require(authenticated_owner_principal==a['owner_principal'] and authenticated_desktop_principal==m['desktop']['principal'], 'independent_authentication_required')
    _require((isinstance(database_url,str) and database_url.strip()) or callable(connect_factory), 'explicit_database_connection_required')
    verify_source_and_candidate(plan)
    from modules.charlie import mission_store as store
    proposed=_bindings(plan)
    with store._connect(database_url or '',connect_factory) as connection:
        _require(not getattr(connection,'autocommit',False), 'transaction_required')
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='3s'"); cursor.execute("set local statement_timeout='10s'")
            for mid in sorted((MISSION_ID,PARENT_ID)):
                cursor.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(mid,))
            rows={mid:ordinary._read_record(cursor,mid,lock=True) for mid in sorted((MISSION_ID,PARENT_ID))}
            cursor.execute(OWNER_HOLD_QUERY,(MISSION_ID,PARENT_ID))
            _require(cursor.fetchone() is None, 'owner_execution_hold_active')
            _require(ordinary._now()<_time(m['expires_at']), 'approval_expired_under_lock')
            _require(rows[PARENT_ID]==m['expected_parent_record'], 'parent_state_changed')
            before=rows[MISSION_ID]; prior=m['expected_registration']
            _require(ordinary._event(cursor,prior['event_id'])==(prior['metadata'],prior['recorded_by'],'workflow_updated'), 'pending_registration_state_changed')
            recorded=ordinary._event(cursor,plan['event_id'])
            original=m['expected_child_record']; admission=original['metadata_json']['mission_admission']
            if recorded:
                h=recorded[0]
                _require(isinstance(h,dict) and set(h)=={'version','manifest','approval',
                    'manifest_sha256','approval_sha256','previous_record','parent_record',
                    'preserved_admission','correction','bindings','updated_metadata'}
                    and recorded[1:]==(a['owner_principal'],'workflow_updated') and h.get('version')==VERSION
                    and h.get('manifest')==m and h.get('approval')==a and h.get('manifest_sha256')==plan['manifest_sha256']
                    and h.get('approval_sha256')==plan['approval_sha256'] and h.get('previous_record')==original
                    and h.get('parent_record')==rows[PARENT_ID] and h.get('preserved_admission')==admission
                    and h.get('bindings')==proposed and isinstance(h.get('correction'),dict)
                    and canonical_event_equal(h['correction'],_correction(plan)), 'replay_history_conflict')
                md=before['metadata_json']; baseline=h.get('updated_metadata') or {}
                _require(ordinary._same_scalar_record(before,original) and baseline=={
                    **original['metadata_json'],**proposed,'mission_control_projection':apply_event_to_projection(
                        {**original,'metadata':{**original['metadata_json'],**proposed}},h['correction'])}
                    and {k:v for k,v in md.items() if k!='mission_admission'}=={k:v for k,v in baseline.items() if k!='mission_admission'}
                    and (md.get('mission_admission')==admission or _later_admission(md.get('mission_admission'),plan)), 'replay_binding_conflict')
                _require(ordinary._latest_correction(cursor)==(h['correction']['event_id'],h['correction'],a['owner_principal']), 'replay_correction_conflict')
                return {'status':'exact_pending_replay','writes':0,'admission_issued':False,'release_performed':False}
            _require(before==original, 'predecessor_state_changed')
            expected=m['expected_correction']
            _require(ordinary._latest_correction(cursor)==(expected['event_id'],expected['metadata'],expected['recorded_by']), 'predecessor_correction_changed')
            correction=_correction(plan)
            _require(correction['event_id']!=expected['event_id'], 'fresh_succession_required')
            cursor.execute("insert into public.charlie_mission_events (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) values(%s,%s,'owner_correction_recorded',%s,%s,%s::jsonb,%s)",
                (correction['event_id'],MISSION_ID,correction['summary'],a['owner_principal'],canonical(correction).decode(),correction['recorded_at']))
            updated={**before['metadata_json'],**proposed}
            updated['mission_control_projection']=apply_event_to_projection({**before,'metadata':updated},correction)
            cursor.execute("update public.charlie_missions m set metadata_json=%s::jsonb,updated_at=now() where mission_id=%s and to_jsonb(m)=%s::jsonb returning mission_id",
                (canonical(updated).decode(),MISSION_ID,canonical(before).decode()))
            _require(cursor.fetchone()==(MISSION_ID,), 'conditional_binding_lost')
            history={'version':VERSION,'manifest':m,'approval':a,'manifest_sha256':plan['manifest_sha256'],
                'approval_sha256':plan['approval_sha256'],'previous_record':before,'parent_record':rows[PARENT_ID],
                'preserved_admission':admission,'correction':correction,'bindings':proposed,'updated_metadata':updated}
            cursor.execute("insert into public.charlie_mission_events (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) values(%s,%s,'workflow_updated',%s,%s,%s::jsonb,now())",
                (plan['event_id'],MISSION_ID,'Owner-approved exact ROOTLINE pending-registration succession.',a['owner_principal'],canonical(history).decode()))
            after=ordinary._read_record(cursor,MISSION_ID)
            _require(ordinary._same_scalar_record(before,after) and after['metadata_json']==updated
                and after['metadata_json']['mission_admission']==admission
                and ordinary._read_record(cursor,PARENT_ID)==rows[PARENT_ID]
                and ordinary._event(cursor,prior['event_id'])==(prior['metadata'],prior['recorded_by'],'workflow_updated')
                and ordinary._event(cursor,plan['event_id'])==(history,a['owner_principal'],'workflow_updated')
                and ordinary._latest_correction(cursor)==(correction['event_id'],correction,a['owner_principal']), 'final_readback_mismatch')
    return {'status':'pending_candidate_succeeded','mission_id':MISSION_ID,'pr_number':CANDIDATE_PR,
        'head_sha':HEAD,'writes':3,'admission_issued':False,'release_performed':False}
