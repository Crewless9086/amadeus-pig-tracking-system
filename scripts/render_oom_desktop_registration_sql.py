"""Prepare bounded HTTPS SQL registration. No database, credential or browser access.

This module never executes SQL. It is not an approval or production operator.
Callers must independently authenticate owner/coordinator and verify the entire
exact package. A copied principal string does not authenticate the caller.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from unittest.mock import patch

from scripts import reconcile_oom_desktop_candidate as adapter
from modules.charlie import mission_store as store

_SQL_SHAPES = frozenset({
    "insert into public.charlie_mission_events (event_id,mission_id,event_type,notes,recorded_by, metadata_json,created_at) values (%(event_id)s,%(mission_id)s, 'owner_correction_recorded',%(notes)s, %(principal)s,%(metadata)s::jsonb,%(created_at)s) on conflict (event_id) do nothing returning event_id",
    "insert into public.charlie_mission_events (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) values(%s,%s,'workflow_updated',%s,%s,%s::jsonb,now())",
    'insert into public.operational_events ( event_id,idempotency_key,schema_version,event_type,domain, aggregate_type,aggregate_id,source_system,source_record_id, authority_tier,privacy_class,actor_type,actor_id,correlation_id, causation_id,occurred_at,recorded_at,freshness_at,payload_json, provenance_json ) values ( %(event_id)s,%(idempotency_key)s,%(schema_version)s,%(event_type)s, %(domain)s,%(aggregate_type)s,%(aggregate_id)s,%(source_system)s, %(source_record_id)s,%(authority_tier)s,%(privacy_class)s, %(actor_type)s,%(actor_id)s,%(correlation_id)s,%(causation_id)s, %(occurred_at)s,%(recorded_at)s,%(freshness_at)s, %(payload)s::jsonb,%(provenance)s::jsonb ) on conflict (idempotency_key) do nothing returning event_id',
    "select coalesce(metadata_json,'{}'::jsonb) from public.charlie_missions where mission_id=%(mission_id)s for update",
    "select event_id,metadata_json,recorded_by from public.charlie_mission_events where mission_id=%s and event_type='owner_correction_recorded' order by created_at desc,event_id desc limit 1",
    'select metadata_json,recorded_by,event_type from public.charlie_mission_events where mission_id=%s and event_id=%s',
    'select to_jsonb(m) from public.charlie_missions m where mission_id=%s',
    'select to_jsonb(m) from public.charlie_missions m where mission_id=%s for update',
    "set local lock_timeout='3s'", "set local statement_timeout='10s'",
    'update public.charlie_missions m set metadata_json=%s::jsonb,updated_at=now() where mission_id=%s and to_jsonb(m)=%s::jsonb returning mission_id',
    'update public.charlie_missions set metadata_json=%(metadata)s::jsonb,updated_at=now() where mission_id=%(mission_id)s',
})


class CaptureDB:
    """Only supplied, already validated preimages; no synthetic default rows."""
    autocommit = False
    def __init__(self, plan):
        m = plan['manifest']
        self.rows = {adapter.MISSION_ID: deepcopy(m['expected_child_record']),
                     adapter.PARENT_ID: deepcopy(m['expected_parent_record'])}
        c = m['expected_correction']
        self.events = {c['event_id']: (deepcopy(c['metadata']), c['recorded_by'], 'owner_correction_recorded')}
        self.ops = {}
        self.commits = self.rollbacks = 0
        self.fail = ''
        self.writes = []

    def cursor(self):
        return CaptureCursor(self)

    def __enter__(self):
        self.before = deepcopy((self.rows,self.events,self.ops))
        return self

    def __exit__(self,kind,*_):
        if kind:
            self.rows,self.events,self.ops=self.before
            self.rollbacks+=1
        else:
            self.commits+=1
        return False


class CaptureCursor:
    """Closed protocol for the current helper; unknown SQL fails before rendering."""
    def __init__(self,db):
        self.db=db
        self.results=[]

    def __enter__(self):
        return self

    def __exit__(self,*_):
        return False

    def execute(self, sql, params=None):
        q=' '.join(sql.split())
        if q not in _SQL_SHAPES:
            raise ValueError('capture_unknown_sql')
        db=self.db
        self.results=[]
        if q.startswith('set local '):
            if q not in {"set local lock_timeout='3s'","set local statement_timeout='10s'"}:
                raise ValueError('capture_unknown_session_setting')
        elif q.startswith('select to_jsonb(m)'):
            self.results=[(deepcopy(db.rows[params[0]]),)]
        elif q.startswith('select event_id,metadata_json,recorded_by'):
            rows=[(key,value[0],value[1]) for key,value in db.events.items() if value[2]=='owner_correction_recorded']
            self.results=sorted(rows,key=lambda row:(row[1]['recorded_at'],row[0]),reverse=True)[:1]
        elif q.startswith('select metadata_json,recorded_by,event_type'):
            if params[1] in db.events:self.results=[deepcopy(db.events[params[1]])]
        elif q.startswith("select coalesce(metadata_json,'{}'::jsonb) from public.charlie_missions"):
            self.results=[(deepcopy(db.rows[params['mission_id']]['metadata_json']),)]
        elif q.startswith('insert into public.charlie_mission_events'):
            if isinstance(params,dict):
                identity=params['event_id']
                if identity in db.events:raise ValueError('capture_partial_correction')
                db.events[identity]=(json.loads(params['metadata']),params['principal'],'owner_correction_recorded')
                self.results=[(identity,)]
            else:
                if params[0] in db.events:raise ValueError('capture_partial_history')
                db.events[params[0]]=(json.loads(params[4]),params[3],'workflow_updated')
            db.writes.append((sql,deepcopy(params)))
        elif q.startswith('insert into public.operational_events'):
            if params['idempotency_key'] in db.ops:raise ValueError('capture_partial_operation')
            db.ops[params['idempotency_key']]=deepcopy(params)
            self.results=[(params['event_id'],)]
            db.writes.append((sql,deepcopy(params)))
        elif q.startswith('update public.charlie_missions'):
            if isinstance(params,dict):
                db.rows[params['mission_id']]['metadata_json']=json.loads(params['metadata'])
                mid=params['mission_id']
            else:
                mid=params[1]
                if db.rows[mid]!=json.loads(params[2]):raise ValueError('capture_conditional_binding_lost')
                db.rows[mid]['metadata_json']=json.loads(params[0])
                self.results=[(mid,)]
            db.rows[mid]['updated_at']=datetime.now(timezone.utc).isoformat()
            db.writes.append((sql,deepcopy(params)))
        else:
            raise ValueError('capture_unknown_sql')

    def fetchone(self):
        return deepcopy(self.results[0]) if self.results else None

    def fetchall(self):
        return deepcopy(self.results)


def capture_plan(arguments, *, authenticated_owner_principal, authenticated_desktop_principal):
    """Reuse original qualified Python code; default source verification remains on."""
    plan = adapter.prepare_reconciliation(**arguments)
    db = CaptureDB(plan)
    # Explicit in-memory transport must not consult DATABASE_URL or credentials.
    with patch.object(store, '_database_url', return_value=''):
        result = adapter.reconcile_candidate(**arguments, dry_run=False,
            authenticated_owner_principal=authenticated_owner_principal,
            authenticated_desktop_principal=authenticated_desktop_principal,
            connect_factory=lambda _: db)
    if result.get('writes') != 5 or len(db.writes) != 5:
        raise ValueError('original_helper_five_write_shape_changed')
    correction = db.writes[0][1]
    operation = db.writes[1][1]
    invalidation = db.writes[2][1]
    binding = db.writes[3][1]
    history = db.writes[4][1]
    if (not isinstance(correction, dict) or not isinstance(operation, dict)
            or not isinstance(invalidation, dict) or not isinstance(binding, tuple)
            or not isinstance(history, tuple)):
        raise ValueError('original_helper_write_parameter_shape_changed')
    updated = json.loads(binding[0])
    recorded_history = json.loads(history[4])
    op_row = {key: value for key, value in operation.items() if key not in {'payload', 'provenance', 'late_event'}}
    op_row['payload_json'] = json.loads(operation['payload'])
    op_row['provenance_json'] = json.loads(operation['provenance'])
    expected_columns = {'event_id','idempotency_key','schema_version','event_type','domain','aggregate_type',
        'aggregate_id','source_system','source_record_id','authority_tier','privacy_class','actor_type','actor_id',
        'correlation_id','causation_id','occurred_at','recorded_at','freshness_at','payload_json','provenance_json'}
    if set(op_row) != expected_columns:
        raise ValueError('operational_event_column_shape_changed')
    return {'plan': plan, 'captured_at': datetime.now(timezone.utc).isoformat(),
        'correction': json.loads(correction['metadata']), 'operational_row': op_row,
        'intermediate_metadata': json.loads(invalidation['metadata']),
        'updated_metadata': updated, 'history': recorded_history, 'history_notes': history[2],
        'original_helper_writes': 5}


def _literal(value):
    raw = adapter.canonical(value).decode()
    index = 0
    while '$registration_payload_' + str(index) + '$' in raw:
        index += 1
    tag = '$registration_payload_' + str(index) + '$'
    return tag + raw + tag + '::jsonb'


def compact_package(captured, *, expected_parent_pg_sha256, expected_child_pg_sha256):
    """Hashes must be computed from exact preimages in disposable PG, never guessed."""
    for value in (expected_parent_pg_sha256, expected_child_pg_sha256):
        if not adapter._sha(value):
            raise ValueError('postgres_preimage_sha256_required')
    compact = deepcopy(captured)
    m = compact['plan']['manifest']
    previous_admission=m['expected_child_record']['metadata_json']['mission_admission']
    invalidated=compact['operational_row']['payload_json']
    if set(previous_admission)-set(invalidated):
        raise ValueError('admission_invalidation_removed_fields')
    compact['invalidation_changes']={key:value for key,value in invalidated.items()
        if key not in previous_admission or previous_admission[key]!=value}
    if {**previous_admission,**compact['invalidation_changes']}!=invalidated:
        raise ValueError('admission_invalidation_delta_mismatch')
    compact['operational_row'].pop('payload_json')
    m.pop('expected_parent_record')
    m.pop('expected_child_record')
    compact['expected_parent_pg_sha256'] = expected_parent_pg_sha256
    compact['expected_child_pg_sha256'] = expected_child_pg_sha256
    compact['binding_changes'] = compact['history']['bindings']
    compact['binding_changes'].pop('mission_admission_contract')
    compact['projection'] = compact['updated_metadata']['mission_control_projection']
    compact.pop('history')
    compact.pop('updated_metadata')
    compact.pop('intermediate_metadata')
    return compact


def _compact_sql_template(template):
    """Strip indentation from trusted SQL code, retaining quoted text/comments.

    The outer anonymous-block delimiter is code structure; any other dollar
    literal is preserved. Run before payload interpolation, never on owner data.
    """
    protected = re.compile(
        r"(?P<text>[eE]'(?:\\.|''|[^'\\])*'|'(?:''|[^'])*'|"
        r'"(?:""|[^"])*"|--[^\r\n]*|/\*[\s\S]*?\*/|'
        r"\$(?!bounded_registration\$)(?P<tag>[A-Za-z_][A-Za-z_0-9]*|)\$"
        r"[\s\S]*?\$(?P=tag)\$)|(?P<indent>^[ \t]+)", re.MULTILINE)
    return protected.sub(lambda match: match.group('text') or '', template)


def render_sql(captured):
    """Anonymous DO block only; package bytes must be reviewed and pinned outside SQL."""
    literal=_literal(captured)
    index=0
    while ('$bounded_registration_'+str(index)+'$') in literal or ('$bounded_registration_'+str(index)+'$') in SQL_TEMPLATE:
        index+=1
    outer_tag='$bounded_registration_'+str(index)+'$'
    if SQL_TEMPLATE.count('$bounded_registration$')!=2 or SQL_TEMPLATE.count('__PINNED_PACKAGE__')!=1:
        raise ValueError('sql_template_delimiter_shape_changed')
    # Replace only the trusted template before inserting arbitrary JSON text.
    # Replacing after interpolation could alter payload text or close DO early.
    template = _compact_sql_template(SQL_TEMPLATE)
    return template.replace('$bounded_registration$',outer_tag).replace('__PINNED_PACKAGE__',literal,1)


SQL_TEMPLATE = r'''-- OFFLINE PREPARATION: NOT AUTHORITY TO EXECUTE.
-- Qualified exact package, independent coordinator authentication and reviewed
-- authenticated same-project HTTPS dashboard are mandatory external gates.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
DO $bounded_registration$
DECLARE
  p jsonb := __PINNED_PACKAGE__;
  m jsonb := p->'plan'->'manifest';
  a jsonb := p->'plan'->'approval';
  child_id text := m->>'mission_id';
  parent_id text := m->>'parent_mission_id';
  registration_event_id text := p->'plan'->>'event_id';
  owner_id text := a->>'owner_principal';
  locked_id text;
  parent_row jsonb;
  before_row jsonb;
  intermediate_row jsonb;
  after_row jsonb;
  original_row jsonb;
  bindings jsonb;
  intermediate_metadata jsonb;
  invalidated_admission jsonb;
  updated_metadata jsonb;
  history jsonb;
  existing_history jsonb;
  existing_actor text;
  existing_kind text;
  latest_correction jsonb;
  latest_actor text;
  latest_id text;
  current_admission jsonb;
  operational_row jsonb;
  expected_operational_row jsonb;
  registration_created_at timestamptz := transaction_timestamp();
  existing_history_created_at timestamptz;
  n integer;
  is_replay boolean := false;
BEGIN
  IF current_database() <> 'postgres' AND current_database() NOT LIKE 'oom_desktop_rebind_test%'
    THEN RAISE EXCEPTION 'database_identity_mismatch'; END IF;
  IF (p->>'original_helper_writes')::integer IS DISTINCT FROM 5
    OR a->>'manifest_sha256' IS DISTINCT FROM p->'plan'->>'manifest_sha256'
    OR a->>'desktop_task_id' IS DISTINCT FROM m->'desktop'->>'task_id'
    OR m->'desktop'->>'principal' IS DISTINCT FROM 'codex_desktop:' || (a->>'desktop_task_id')
    THEN RAISE EXCEPTION 'package_identity_mismatch'; END IF;
  -- This omitted insert field is a canonical database-owned transaction clock.
  -- Refuse a different schema/default rather than excluding it from row checks.
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute c
      JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.attrelid AND d.adnum=c.attnum
      WHERE c.attrelid='public.operational_events'::regclass AND c.attname='created_at'
      AND NOT c.attisdropped AND c.atttypid='timestamptz'::regtype AND c.atttypmod=-1 AND c.attnotnull
      AND c.attgenerated='' AND c.attidentity=''
      AND pg_catalog.pg_get_expr(d.adbin,d.adrelid)='now()')
    THEN RAISE EXCEPTION 'operational_created_at_schema_mismatch'; END IF;
  -- Same lock used by canonical hold creation; ordering is shared by both missions.
  FOR locked_id IN SELECT value FROM unnest(ARRAY[parent_id,child_id]) AS u(value) ORDER BY value LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended(locked_id,0));
  END LOOP;
  FOR locked_id IN SELECT mission_id FROM public.charlie_missions
    WHERE mission_id IN (parent_id,child_id) ORDER BY mission_id FOR UPDATE LOOP
    NULL;
  END LOOP;
  IF NOT (clock_timestamp() >= (a->>'issued_at')::timestamptz
    AND clock_timestamp() < (a->>'expires_at')::timestamptz
    AND (a->>'expires_at')::timestamptz = (m->>'expires_at')::timestamptz)
    THEN RAISE EXCEPTION 'approval_expired_under_lock'; END IF;
  IF EXISTS (SELECT 1 FROM public.charlie_owner_execution_hold_events h
      WHERE h.mission_id IN (parent_id,child_id) AND h.event_type='hold_created'
      AND NOT EXISTS (SELECT 1 FROM public.charlie_owner_execution_hold_events r
        WHERE r.event_type='hold_released' AND r.release_of_event_id=h.event_id))
    THEN RAISE EXCEPTION 'owner_execution_hold_active'; END IF;
  SELECT to_jsonb(x) INTO parent_row FROM public.charlie_missions x WHERE x.mission_id=parent_id;
  SELECT to_jsonb(x) INTO before_row FROM public.charlie_missions x WHERE x.mission_id=child_id;
  IF before_row IS NULL THEN RAISE EXCEPTION 'mission_record_unavailable'; END IF;
  SELECT x.metadata_json,x.recorded_by,x.event_type,x.created_at
    INTO existing_history,existing_actor,existing_kind,existing_history_created_at
    FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_id=registration_event_id;
  IF p ? 'expected_parent_pg_sha256' THEN
    IF encode(sha256(convert_to(parent_row::text,'UTF8')),'hex') IS DISTINCT FROM p->>'expected_parent_pg_sha256'
      THEN RAISE EXCEPTION 'parent_state_changed'; END IF;
    original_row := CASE WHEN existing_history IS NULL THEN before_row ELSE existing_history->'previous_record' END;
    IF encode(sha256(convert_to(original_row::text,'UTF8')),'hex') IS DISTINCT FROM p->>'expected_child_pg_sha256'
      THEN RAISE EXCEPTION 'predecessor_state_changed'; END IF;
    m := m || jsonb_build_object('expected_parent_record',parent_row,'expected_child_record',original_row);
    p := jsonb_set(p,'{plan,manifest}',m);
    bindings := (p->'binding_changes') || jsonb_build_object('mission_admission_contract',m->'contract');
    invalidated_admission := (original_row->'metadata_json'->'mission_admission') || (p->'invalidation_changes');
    p := jsonb_set(p,'{operational_row,payload_json}',invalidated_admission);
    intermediate_metadata := (original_row->'metadata_json') || jsonb_build_object('mission_admission',p->'operational_row'->'payload_json');
    updated_metadata := intermediate_metadata || bindings || jsonb_build_object('mission_control_projection',p->'projection');
    history := jsonb_build_object('version',m->>'version','manifest',m,'approval',a,
      'manifest_sha256',p->'plan'->>'manifest_sha256','approval_sha256',p->'plan'->>'approval_sha256',
      'previous_record',original_row,'parent_record',parent_row,'correction',p->'correction',
      'invalidated_admission',p->'operational_row'->'payload_json','bindings',bindings);
    p := p || jsonb_build_object('intermediate_metadata',intermediate_metadata,'updated_metadata',updated_metadata,'history',history);
  ELSE
    IF parent_row IS DISTINCT FROM m->'expected_parent_record'
      THEN RAISE EXCEPTION 'parent_state_changed'; END IF;
  END IF;
  SELECT x.event_id,x.metadata_json,x.recorded_by INTO latest_id,latest_correction,latest_actor
    FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_type='owner_correction_recorded'
    ORDER BY x.created_at DESC,x.event_id DESC LIMIT 1;
  SELECT to_jsonb(x) INTO operational_row FROM public.operational_events x
    WHERE x.idempotency_key=p->'operational_row'->>'idempotency_key';
  IF existing_history IS NOT NULL THEN
    IF existing_history IS DISTINCT FROM p->'history' OR existing_actor IS DISTINCT FROM owner_id
      OR existing_kind IS DISTINCT FROM 'workflow_updated'
      THEN RAISE EXCEPTION 'replay_history_conflict'; END IF;
    IF before_row - ARRAY['metadata_json','updated_at'] IS DISTINCT FROM
        (m->'expected_child_record') - ARRAY['metadata_json','updated_at']
      OR (before_row->'metadata_json') - 'mission_admission' IS DISTINCT FROM
        (p->'updated_metadata') - 'mission_admission'
      THEN RAISE EXCEPTION 'replay_binding_conflict'; END IF;
    IF latest_id IS DISTINCT FROM p->'correction'->>'event_id'
      OR latest_correction IS DISTINCT FROM p->'correction' OR latest_actor IS DISTINCT FROM owner_id
      THEN RAISE EXCEPTION 'replay_correction_conflict'; END IF;
    current_admission := before_row->'metadata_json'->'mission_admission';
    IF current_admission IS DISTINCT FROM p->'history'->'invalidated_admission' AND (
      current_admission->>'mission_id'=child_id
      AND current_admission->>'root_mission_id'=p->'history'->'bindings'->'mission_family'->>'root_mission_id'
      AND current_admission->>'generation'=m->>'generation'
      AND current_admission->>'base_sha'=m->'candidate'->>'base_sha'
      AND current_admission->>'head_sha'=m->'candidate'->>'head_sha'
      AND jsonb_typeof(current_admission->'signed_receipt')='object') IS NOT TRUE
      THEN RAISE EXCEPTION 'replay_admission_conflict'; END IF;
    registration_created_at := existing_history_created_at;
    IF registration_created_at IS NULL
      OR registration_created_at < (a->>'issued_at')::timestamptz
      OR registration_created_at >= (a->>'expires_at')::timestamptz
      OR registration_created_at > clock_timestamp()
      THEN RAISE EXCEPTION 'replay_registration_timestamp_conflict'; END IF;
    expected_operational_row := to_jsonb(jsonb_populate_record(NULL::public.operational_events,
      (p->'operational_row') || jsonb_build_object('created_at',registration_created_at)));
    IF operational_row IS DISTINCT FROM expected_operational_row
      THEN RAISE EXCEPTION 'replay_operational_audit_conflict'; END IF;
    is_replay := true;
  ELSE
    IF before_row IS DISTINCT FROM m->'expected_child_record'
      THEN RAISE EXCEPTION 'predecessor_state_changed'; END IF;
    IF latest_id IS DISTINCT FROM m->'expected_correction'->>'event_id'
      OR latest_correction IS DISTINCT FROM m->'expected_correction'->'metadata'
      OR latest_actor IS DISTINCT FROM m->'expected_correction'->>'recorded_by'
      THEN RAISE EXCEPTION 'predecessor_correction_changed'; END IF;
    IF operational_row IS NOT NULL OR EXISTS(SELECT 1 FROM public.charlie_mission_events x
      WHERE x.event_id IN (registration_event_id,p->'correction'->>'event_id'))
      THEN RAISE EXCEPTION 'partial_audit_conflict'; END IF;
    IF registration_created_at < (a->>'issued_at')::timestamptz
      OR registration_created_at >= (a->>'expires_at')::timestamptz
      THEN RAISE EXCEPTION 'registration_timestamp_outside_approval'; END IF;
    expected_operational_row := to_jsonb(jsonb_populate_record(NULL::public.operational_events,
      (p->'operational_row') || jsonb_build_object('created_at',registration_created_at)));

    INSERT INTO public.charlie_mission_events(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
      VALUES(p->'correction'->>'event_id',child_id,'owner_correction_recorded',p->'correction'->>'summary',
        owner_id,p->'correction',(p->'correction'->>'recorded_at')::timestamptz);
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'correction_write_count'; END IF;
    INSERT INTO public.operational_events(event_id,idempotency_key,schema_version,event_type,domain,aggregate_type,
      aggregate_id,source_system,source_record_id,authority_tier,privacy_class,actor_type,actor_id,correlation_id,
      causation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json)
      SELECT x.event_id,x.idempotency_key,x.schema_version,x.event_type,x.domain,x.aggregate_type,x.aggregate_id,
        x.source_system,x.source_record_id,x.authority_tier,x.privacy_class,x.actor_type,x.actor_id,x.correlation_id,
        x.causation_id,x.occurred_at,x.recorded_at,x.freshness_at,x.payload_json,x.provenance_json
      FROM jsonb_populate_record(NULL::public.operational_events,p->'operational_row') x;
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'operational_write_count'; END IF;
    UPDATE public.charlie_missions x SET metadata_json=p->'intermediate_metadata',updated_at=now()
      WHERE x.mission_id=child_id AND to_jsonb(x)=before_row;
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'conditional_invalidation_lost'; END IF;
    SELECT to_jsonb(x) INTO intermediate_row FROM public.charlie_missions x WHERE x.mission_id=child_id;
    IF intermediate_row - ARRAY['metadata_json','updated_at'] IS DISTINCT FROM before_row - ARRAY['metadata_json','updated_at']
      OR intermediate_row->'metadata_json' IS DISTINCT FROM p->'intermediate_metadata'
      OR (intermediate_row->>'updated_at')::timestamptz IS DISTINCT FROM registration_created_at
      THEN RAISE EXCEPTION 'invalidation_readback_mismatch'; END IF;
    UPDATE public.charlie_missions x SET metadata_json=p->'updated_metadata',updated_at=now()
      WHERE x.mission_id=child_id AND to_jsonb(x)=intermediate_row;
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'conditional_binding_lost'; END IF;
    INSERT INTO public.charlie_mission_events(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
      VALUES(registration_event_id,child_id,'workflow_updated',p->>'history_notes',owner_id,p->'history',now());
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'history_write_count'; END IF;
  END IF;
  SELECT to_jsonb(x) INTO after_row FROM public.charlie_missions x WHERE x.mission_id=child_id;
  IF after_row - ARRAY['metadata_json','updated_at'] IS DISTINCT FROM before_row - ARRAY['metadata_json','updated_at']
    OR (NOT is_replay AND (after_row->'metadata_json' IS DISTINCT FROM p->'updated_metadata'
      OR (after_row->>'updated_at')::timestamptz IS DISTINCT FROM registration_created_at))
    OR (is_replay AND after_row IS DISTINCT FROM before_row)
    OR (SELECT to_jsonb(x) FROM public.charlie_missions x WHERE x.mission_id=parent_id) IS DISTINCT FROM parent_row
    OR NOT EXISTS(SELECT 1 FROM public.charlie_mission_events x WHERE x.event_id=registration_event_id AND x.mission_id=child_id
      AND x.event_type='workflow_updated' AND x.recorded_by=owner_id AND x.metadata_json=p->'history'
      AND x.created_at=registration_created_at)
    OR NOT EXISTS(SELECT 1 FROM public.charlie_mission_events x WHERE x.event_id=p->'correction'->>'event_id'
      AND x.mission_id=child_id AND x.event_type='owner_correction_recorded' AND x.recorded_by=owner_id
      AND x.metadata_json=p->'correction' AND x.created_at=(p->'correction'->>'recorded_at')::timestamptz)
    OR (SELECT jsonb_build_object('event_id',x.event_id,'metadata',x.metadata_json,'recorded_by',x.recorded_by)
      FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_type='owner_correction_recorded'
      ORDER BY x.created_at DESC,x.event_id DESC LIMIT 1) IS DISTINCT FROM jsonb_build_object(
        'event_id',p->'correction'->>'event_id','metadata',p->'correction','recorded_by',owner_id)
    OR (SELECT to_jsonb(x) FROM public.operational_events x WHERE x.idempotency_key=p->'operational_row'->>'idempotency_key')
      IS DISTINCT FROM expected_operational_row
    THEN RAISE EXCEPTION 'final_readback_mismatch'; END IF;
  PERFORM set_config('amadeus.registration_result',jsonb_build_object('status',
    CASE WHEN is_replay THEN 'exact_replay' ELSE 'candidate_reconciled' END,
    'writes',CASE WHEN is_replay THEN 0 ELSE 5 END,'parent_unchanged',true,
    'manifest_sha256',p->'plan'->>'manifest_sha256','head_sha',m->'candidate'->>'head_sha')::text,true);
END
$bounded_registration$;
SELECT current_setting('amadeus.registration_result')::jsonb AS registration_result;
COMMIT;
'''


# The pending successor has its own capture/renderer; the original five-write
# helper and SQL_TEMPLATE above remain byte-for-byte unchanged.
_PENDING_CORRECTION_SQL = "insert into public.charlie_mission_events (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) values(%s,%s,'owner_correction_recorded',%s,%s,%s::jsonb,%s)"
_PENDING_HISTORY_SQL = "insert into public.charlie_mission_events (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) values(%s,%s,'workflow_updated',%s,%s,%s::jsonb,now())"
_PENDING_BINDING_SQL = 'update public.charlie_missions m set metadata_json=%s::jsonb,updated_at=now() where mission_id=%s and to_jsonb(m)=%s::jsonb returning mission_id'


class PendingCaptureDB(CaptureDB):
    def __init__(self, plan):
        super().__init__(plan)
        r=plan['manifest']['expected_registration']
        self.events[r['event_id']] = (deepcopy(r['metadata']),r['recorded_by'],'workflow_updated')
    def cursor(self): return PendingCaptureCursor(self)


class PendingCaptureCursor(CaptureCursor):
    def execute(self,sql,params=None):
        from scripts import reconcile_rootline_pending_registration as pending
        q=' '.join(sql.split())
        if q in {'select pg_advisory_xact_lock(hashtextextended(%s,0))',pending.OWNER_HOLD_QUERY}:
            # No live state is inferred: capture models only validated preimages.
            # The resulting SQL always checks real holds under advisory locks.
            self.results=[];return
        allowed={x for x in _SQL_SHAPES if x.startswith(('select to_jsonb(m)',
            'select event_id,metadata_json,recorded_by','select metadata_json,recorded_by,event_type','set local '))}
        allowed|={_PENDING_CORRECTION_SQL,_PENDING_BINDING_SQL,_PENDING_HISTORY_SQL}
        if q not in allowed:raise ValueError('pending_capture_unknown_sql')
        if q==_PENDING_CORRECTION_SQL:
            if params[0] in self.db.events:raise ValueError('pending_capture_partial_correction')
            self.db.events[params[0]]=(json.loads(params[4]),params[3],'owner_correction_recorded')
            self.db.writes.append((sql,deepcopy(params)));self.results=[];return
        super().execute(sql,params)


def capture_pending_plan(arguments, *, authenticated_owner_principal, authenticated_desktop_principal):
    from scripts import reconcile_rootline_pending_registration as pending
    plan=pending.prepare_pending_succession(**arguments)
    db=PendingCaptureDB(plan)
    with patch.object(store,'_database_url',return_value=''):
        result=pending.reconcile_pending_succession(**arguments,dry_run=False,
            authenticated_owner_principal=authenticated_owner_principal,
            authenticated_desktop_principal=authenticated_desktop_principal,connect_factory=lambda _:db)
    if result.get('writes')!=3 or [' '.join(q.split()) for q,_ in db.writes]!=[
        _PENDING_CORRECTION_SQL,_PENDING_BINDING_SQL,_PENDING_HISTORY_SQL]:
        raise ValueError('pending_helper_three_write_shape_changed')
    correction,binding,history=[params for _,params in db.writes]
    return {'shape':pending.VERSION,'original_helper_writes':3,'plan':plan,
        'correction':json.loads(correction[4]),'updated_metadata':json.loads(binding[0]),
        'history':json.loads(history[4]),'history_notes':history[2]}


def _validate_pending_package(package):
    from scripts import reconcile_rootline_pending_registration as pending
    from modules.charlie.mission_control import build_mission_control_event,apply_event_to_projection
    if set(package)!={'shape','original_helper_writes','plan','correction','updated_metadata','history','history_notes'}:
        raise ValueError('pending_package_fields')
    plan=package['plan'];m,a=plan['manifest'],plan['approval']
    expected=pending.prepare_pending_succession(pending.canonical(m),pending.canonical(a),
        expected_manifest_sha256=plan['manifest_sha256'],expected_approval_sha256=plan['approval_sha256'])
    if plan!=expected or package['shape']!=pending.VERSION or type(package['original_helper_writes']) is not int or package['original_helper_writes']!=3:
        raise ValueError('pending_package_identity')
    correction=pending._correction(plan,now=pending._time(package['correction']['recorded_at']))
    if correction!=package['correction'] or not pending._time(a['issued_at'])<=pending._time(correction['recorded_at'])<pending._time(a['expires_at']):
        raise ValueError('pending_package_correction')
    bindings=pending._bindings(plan);before=m['expected_child_record'];updated={**before['metadata_json'],**bindings}
    updated['mission_control_projection']=apply_event_to_projection({**before,'metadata':updated},correction)
    history={'version':pending.VERSION,'manifest':m,'approval':a,'manifest_sha256':plan['manifest_sha256'],
        'approval_sha256':plan['approval_sha256'],'previous_record':before,'parent_record':m['expected_parent_record'],
        'preserved_admission':before['metadata_json']['mission_admission'],'correction':correction,
        'bindings':bindings,'updated_metadata':updated}
    if package['updated_metadata']!=updated or package['history']!=history or package['history_notes']!='Owner-approved exact ROOTLINE pending-registration succession.':
        raise ValueError('pending_package_postimage')


def compact_pending_package(package, *, expected_parent_pg_sha256, expected_child_pg_sha256,
                            expected_registration_pg_sha256):
    """Keep transfer limits; exact PostgreSQL hashes must come from canonical rows."""
    _validate_pending_package(package)
    for value in (expected_parent_pg_sha256,expected_child_pg_sha256,expected_registration_pg_sha256):
        if not adapter._sha(value):raise ValueError('postgres_preimage_sha256_required')
    compact=deepcopy(package);m=compact['plan']['manifest']
    m.pop('expected_parent_record');m.pop('expected_child_record')
    m['expected_registration'].pop('metadata')
    compact['expected_parent_pg_sha256']=expected_parent_pg_sha256
    compact['expected_child_pg_sha256']=expected_child_pg_sha256
    compact['expected_registration_pg_sha256']=expected_registration_pg_sha256
    compact['binding_changes']=compact['history']['bindings']
    compact['binding_changes'].pop('mission_admission_contract')
    compact['projection']=compact['updated_metadata']['mission_control_projection']
    compact.pop('history');compact.pop('updated_metadata')
    return compact


def render_pending_sql(package, **postgres_hashes):
    """Render only. Optional compact form is built from a fully validated package."""
    _validate_pending_package(package)
    if postgres_hashes:package=compact_pending_package(package,**postgres_hashes)
    literal=_literal(package);index=0
    while '$pending_registration_'+str(index)+'$' in literal:index+=1
    delimiter='$pending_registration_'+str(index)+'$'
    return _compact_sql_template(PENDING_SQL_TEMPLATE).replace('$pending_registration$',delimiter).replace('__PENDING_PACKAGE__',literal)


PENDING_SQL_TEMPLATE = r"""-- OFFLINE PREPARATION ONLY; independent exact owner approval is mandatory.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
DO $pending_registration$
DECLARE
  p jsonb := __PENDING_PACKAGE__;
  m jsonb := p->'plan'->'manifest';
  a jsonb := p->'plan'->'approval';
  child_id text := m->>'mission_id';
  parent_id text := m->>'parent_mission_id';
  owner_id text := a->>'owner_principal';
  registration_id text := p->'plan'->>'event_id';
  locked_id text;
  parent_row jsonb;
  before_row jsonb;
  after_row jsonb;
  original_row jsonb;
  bindings jsonb;
  updated_metadata jsonb;
  history jsonb;
  old_history jsonb;
  old_actor text;
  old_kind text;
  current_history jsonb;
  current_actor text;
  current_kind text;
  current_admission jsonb;
  latest_correction jsonb;
  latest_id text;
  latest_actor text;
  registration_time timestamptz := transaction_timestamp();
  n integer;
  is_replay boolean := false;
BEGIN
  IF current_database()<>'postgres' AND current_database() NOT LIKE 'oom_desktop_rebind_test%'
    THEN RAISE EXCEPTION 'database_identity_mismatch'; END IF;
  IF p->>'shape' IS DISTINCT FROM 'rootline_pending_registration_successor_v1'
    OR p->>'original_helper_writes' IS DISTINCT FROM '3'
    OR m->>'version' IS DISTINCT FROM p->>'shape'
    OR a->>'version' IS DISTINCT FROM p->>'shape'
    OR a->>'decision' IS DISTINCT FROM 'succeed_exact_pending_pr1404_registration_with_rootline_pr1405'
    OR child_id IS DISTINCT FROM 'OMQ-20260813-03-MORNING-CONTAINMENT'
    OR parent_id IS DISTINCT FROM 'OMQ-20260813-03'
    OR m->'candidate'->>'head_sha' IS DISTINCT FROM 'cb9f89442a472bff3711740cb11d823777104679'
    OR m->'candidate'->>'base_sha' IS DISTINCT FROM '18de462e8463b44b289b29eda3693606d9b1e43a'
    OR m->'candidate'->>'pr_number' IS DISTINCT FROM '1405'
    OR a->>'manifest_sha256' IS DISTINCT FROM p->'plan'->>'manifest_sha256'
    OR m->'desktop'->>'principal' IS DISTINCT FROM 'codex_desktop:'||(a->>'desktop_task_id')
    THEN RAISE EXCEPTION 'pending_package_identity'; END IF;
  FOR locked_id IN SELECT value FROM unnest(ARRAY[parent_id,child_id]) AS u(value) ORDER BY value LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended(locked_id,0));
  END LOOP;
  FOR locked_id IN SELECT mission_id FROM public.charlie_missions WHERE mission_id IN(parent_id,child_id) ORDER BY mission_id FOR UPDATE LOOP NULL; END LOOP;
  IF NOT(clock_timestamp()>=(a->>'issued_at')::timestamptz AND clock_timestamp()<(a->>'expires_at')::timestamptz
    AND (a->>'expires_at')::timestamptz=(m->>'expires_at')::timestamptz)
    THEN RAISE EXCEPTION 'approval_expired_under_lock'; END IF;
  IF EXISTS(SELECT 1 FROM public.charlie_owner_execution_hold_events h WHERE h.mission_id IN(parent_id,child_id)
    AND h.event_type='hold_created' AND NOT EXISTS(SELECT 1 FROM public.charlie_owner_execution_hold_events r
      WHERE r.event_type='hold_released' AND r.release_of_event_id=h.event_id))
    THEN RAISE EXCEPTION 'owner_execution_hold_active'; END IF;
  SELECT to_jsonb(x) INTO parent_row FROM public.charlie_missions x WHERE x.mission_id=parent_id;
  SELECT to_jsonb(x) INTO before_row FROM public.charlie_missions x WHERE x.mission_id=child_id;
  IF before_row IS NULL THEN RAISE EXCEPTION 'mission_record_unavailable'; END IF;
  IF p ? 'expected_parent_pg_sha256' THEN
    IF encode(sha256(convert_to(parent_row::text,'UTF8')),'hex') IS DISTINCT FROM p->>'expected_parent_pg_sha256'
      THEN RAISE EXCEPTION 'parent_state_changed'; END IF;
  ELSIF parent_row IS DISTINCT FROM m->'expected_parent_record' THEN RAISE EXCEPTION 'parent_state_changed'; END IF;
  SELECT x.metadata_json,x.recorded_by,x.event_type INTO old_history,old_actor,old_kind
    FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_id=m->'expected_registration'->>'event_id';
  IF (CASE WHEN p ? 'expected_registration_pg_sha256' THEN
      encode(sha256(convert_to(old_history::text,'UTF8')),'hex') IS DISTINCT FROM p->>'expected_registration_pg_sha256'
    ELSE old_history IS DISTINCT FROM m->'expected_registration'->'metadata' END)
    OR old_actor IS DISTINCT FROM m->'expected_registration'->>'recorded_by' OR old_kind IS DISTINCT FROM 'workflow_updated'
    THEN RAISE EXCEPTION 'pending_registration_state_changed'; END IF;
  SELECT x.event_id,x.metadata_json,x.recorded_by INTO latest_id,latest_correction,latest_actor
    FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_type='owner_correction_recorded'
    ORDER BY x.created_at DESC,x.event_id DESC LIMIT 1;
  SELECT x.metadata_json,x.recorded_by,x.event_type INTO current_history,current_actor,current_kind
    FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_id=registration_id;
  IF p ? 'expected_child_pg_sha256' THEN
    original_row:=CASE WHEN current_history IS NULL THEN before_row ELSE current_history->'previous_record' END;
    IF encode(sha256(convert_to(original_row::text,'UTF8')),'hex') IS DISTINCT FROM p->>'expected_child_pg_sha256'
      THEN RAISE EXCEPTION 'predecessor_state_changed'; END IF;
    m:=m||jsonb_build_object('expected_parent_record',parent_row,'expected_child_record',original_row);
    m:=jsonb_set(m,'{expected_registration,metadata}',old_history);
    p:=jsonb_set(p,'{plan,manifest}',m);
    bindings:=(p->'binding_changes')||jsonb_build_object('mission_admission_contract',m->'contract');
    updated_metadata:=(original_row->'metadata_json')||bindings||jsonb_build_object('mission_control_projection',p->'projection');
    history:=jsonb_build_object('version',m->>'version','manifest',m,'approval',a,
      'manifest_sha256',p->'plan'->>'manifest_sha256','approval_sha256',p->'plan'->>'approval_sha256',
      'previous_record',original_row,'parent_record',parent_row,
      'preserved_admission',original_row->'metadata_json'->'mission_admission',
      'correction',p->'correction','bindings',bindings,'updated_metadata',updated_metadata);
    p:=p||jsonb_build_object('updated_metadata',updated_metadata,'history',history);
  END IF;
  IF current_history IS NOT NULL THEN
    IF current_history IS DISTINCT FROM p->'history' OR current_actor IS DISTINCT FROM owner_id OR current_kind IS DISTINCT FROM 'workflow_updated'
      THEN RAISE EXCEPTION 'replay_history_conflict'; END IF;
    IF before_row-ARRAY['metadata_json','updated_at'] IS DISTINCT FROM (m->'expected_child_record')-ARRAY['metadata_json','updated_at']
      OR (before_row->'metadata_json')-'mission_admission' IS DISTINCT FROM (p->'updated_metadata')-'mission_admission'
      THEN RAISE EXCEPTION 'replay_binding_conflict'; END IF;
    current_admission:=before_row->'metadata_json'->'mission_admission';
    IF current_admission IS DISTINCT FROM p->'history'->'preserved_admission' AND (
      current_admission->>'status' IN('valid','consumed','revoked','invalidated')
      AND current_admission->>'mission_id'=child_id AND current_admission->>'root_mission_id'=parent_id
      AND current_admission->>'generation'=m->>'generation' AND current_admission->>'head_sha'=m->'candidate'->>'head_sha'
      AND current_admission->>'base_sha'=m->'candidate'->>'base_sha'
      AND jsonb_typeof(current_admission->'signed_receipt')='object'
      AND current_admission->'signed_receipt'->'mission'=jsonb_build_object('mission_id',child_id,'root_mission_id',parent_id,'generation',m->>'generation')
      AND current_admission->'signed_receipt'->'candidate'->>'head_sha'=current_admission->>'head_sha'
      AND current_admission->'signed_receipt'->'candidate'->>'base_sha'=current_admission->>'base_sha'
      AND current_admission->>'content_sha256' ~ '^[0-9a-f]{64}$'
      AND current_admission->>'authority_key_sha256' ~ '^[0-9a-f]{64}$'
      AND current_admission->'signed_receipt'->>'content_sha256'=current_admission->>'content_sha256'
      AND current_admission->'signed_receipt'->>'authority_key_sha256'=current_admission->>'authority_key_sha256'
      AND current_admission->'signed_receipt'->>'receipt_id'=current_admission->>'receipt_id') IS NOT TRUE
      THEN RAISE EXCEPTION 'replay_binding_conflict'; END IF;
    IF latest_id IS DISTINCT FROM p->'correction'->>'event_id' OR latest_correction IS DISTINCT FROM p->'correction' OR latest_actor IS DISTINCT FROM owner_id
      THEN RAISE EXCEPTION 'replay_correction_conflict'; END IF;
    is_replay:=true;
  ELSE
    IF before_row IS DISTINCT FROM m->'expected_child_record' THEN RAISE EXCEPTION 'predecessor_state_changed'; END IF;
    IF latest_id IS DISTINCT FROM m->'expected_correction'->>'event_id'
      OR latest_correction IS DISTINCT FROM m->'expected_correction'->'metadata'
      OR latest_actor IS DISTINCT FROM m->'expected_correction'->>'recorded_by'
      THEN RAISE EXCEPTION 'predecessor_correction_changed'; END IF;
    IF EXISTS(SELECT 1 FROM public.charlie_mission_events x WHERE x.event_id IN(registration_id,p->'correction'->>'event_id'))
      THEN RAISE EXCEPTION 'partial_audit_conflict'; END IF;
    IF registration_time<(a->>'issued_at')::timestamptz OR registration_time>=(a->>'expires_at')::timestamptz
      THEN RAISE EXCEPTION 'registration_timestamp_outside_approval'; END IF;
    INSERT INTO public.charlie_mission_events(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
      VALUES(p->'correction'->>'event_id',child_id,'owner_correction_recorded',p->'correction'->>'summary',owner_id,p->'correction',(p->'correction'->>'recorded_at')::timestamptz);
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'correction_write_count'; END IF;
    UPDATE public.charlie_missions x SET metadata_json=p->'updated_metadata',updated_at=now()
      WHERE x.mission_id=child_id AND to_jsonb(x)=before_row;
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'conditional_binding_lost'; END IF;
    INSERT INTO public.charlie_mission_events(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
      VALUES(registration_id,child_id,'workflow_updated',p->>'history_notes',owner_id,p->'history',now());
    GET DIAGNOSTICS n=ROW_COUNT;
    IF n<>1 THEN RAISE EXCEPTION 'history_write_count'; END IF;
  END IF;
  SELECT to_jsonb(x) INTO after_row FROM public.charlie_missions x WHERE x.mission_id=child_id;
  IF after_row-ARRAY['metadata_json','updated_at'] IS DISTINCT FROM before_row-ARRAY['metadata_json','updated_at']
    OR (NOT is_replay AND (after_row->'metadata_json' IS DISTINCT FROM p->'updated_metadata'
      OR after_row->'metadata_json'->'mission_admission' IS DISTINCT FROM m->'expected_child_record'->'metadata_json'->'mission_admission'
      OR (after_row->>'updated_at')::timestamptz IS DISTINCT FROM registration_time))
    OR (is_replay AND after_row IS DISTINCT FROM before_row)
    OR (SELECT to_jsonb(x) FROM public.charlie_missions x WHERE x.mission_id=parent_id) IS DISTINCT FROM parent_row
    OR NOT EXISTS(SELECT 1 FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_id=registration_id
      AND x.event_type='workflow_updated' AND x.recorded_by=owner_id AND x.metadata_json=p->'history')
    OR NOT EXISTS(SELECT 1 FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_id=p->'correction'->>'event_id'
      AND x.event_type='owner_correction_recorded' AND x.recorded_by=owner_id AND x.metadata_json=p->'correction'
      AND x.created_at=(p->'correction'->>'recorded_at')::timestamptz)
    OR NOT EXISTS(SELECT 1 FROM public.charlie_mission_events x WHERE x.mission_id=child_id AND x.event_id=m->'expected_registration'->>'event_id'
      AND x.event_type='workflow_updated' AND x.recorded_by=old_actor AND x.metadata_json=old_history)
    THEN RAISE EXCEPTION 'final_readback_mismatch'; END IF;
  PERFORM set_config('amadeus.pending_registration_result',jsonb_build_object('status',
    CASE WHEN is_replay THEN 'exact_pending_replay' ELSE 'pending_candidate_succeeded' END,
    'writes',CASE WHEN is_replay THEN 0 ELSE 3 END,'parent_unchanged',true,
    'manifest_sha256',p->'plan'->>'manifest_sha256','head_sha',m->'candidate'->>'head_sha')::text,true);
END
$pending_registration$;
SELECT current_setting('amadeus.pending_registration_result')::jsonb AS registration_result;
COMMIT;
"""
