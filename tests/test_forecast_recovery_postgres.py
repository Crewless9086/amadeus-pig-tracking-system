"""Root-only qualification against existing migrated loopback tables.

Never creates or truncates a schema. Source fields and only the snapshots made
by this fixture are restored under the root's exclusive disposable-DB lease.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from modules.telemetry import forecast_provider_health as health


@pytest.fixture
def recovery_pg(monkeypatch, request):
    if os.getenv('ROOTLINE_FORECAST_RECOVERY_PG_ENABLED') != '1':
        pytest.skip('root-only loopback transaction qualification is not enabled')
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    url = os.getenv('ROOTLINE_FORECAST_RECOVERY_TEST_DATABASE_URL', '')
    info = conninfo_to_dict(url)
    assert info.get('host') == '127.0.0.1'
    assert info.get('port') == '55485'
    assert info.get('dbname') == 'rootline_ha_command_mode_test'
    assert not info.get('hostaddr') and not info.get('service')
    monkeypatch.setenv(health.INGEST_API_KEY_ENV, 'offline-forecast42-key')
    def connect():
        return psycopg.connect(url, connect_timeout=3,
            options='-c statement_timeout=3000 -c lock_timeout=1000')
    sources = [health.SOURCES[p] for p in ('visual_crossing', 'weatherapi')]
    originals = {}
    snapshots = []
    def restore():
        with connect() as db:
            for source, run_at in snapshots:
                db.execute('delete from public.weather_forecast_snapshots where source_id=%s and forecast_run_at=%s', (source, run_at))
            for source, prior in originals.items():
                if prior is None:
                    db.execute('delete from public.telemetry_sources where source_id=%s', (source,))
                else:
                    db.execute('update public.telemetry_sources set provider=%s,source_type=%s,active=%s,metadata=%s::jsonb,updated_at=%s where source_id=%s',
                        (*prior[:3], json.dumps(prior[3]), prior[4], source))
    request.addfinalizer(restore)
    with connect() as db:
        assert db.execute("select to_regclass('public.telemetry_sources'),to_regclass('public.weather_forecast_snapshots')").fetchone() == ('telemetry_sources', 'weather_forecast_snapshots')
        for provider in ('visual_crossing', 'weatherapi'):
            source = health.SOURCES[provider]
            originals[source] = db.execute('select provider,source_type,active,metadata,updated_at from public.telemetry_sources where source_id=%s', (source,)).fetchone()
            db.execute("""insert into public.telemetry_sources(source_id,provider,source_type,active,display_name,metadata)
                values(%s,%s,'forecast',true,'Offline forecast42 qualification','{"unrelated":"preserved"}')
                on conflict(source_id) do update set provider=excluded.provider,source_type=excluded.source_type,
                    active=true,metadata=excluded.metadata""", (source, provider))
        now = db.execute('select clock_timestamp()').fetchone()[0]
    local = now.astimezone(ZoneInfo('Africa/Johannesburg'))
    boundary = local.replace(hour=23, minute=30, second=0, microsecond=0)
    if boundary > local:
        boundary -= timedelta(days=1)
    original_transition = health.nightly_transition
    def at_admission(state, request, now):
        return original_transition(state, request, boundary.astimezone(timezone.utc)
            if request.get('action') == 'nightly_claim' else now)
    monkeypatch.setattr(health, 'nightly_transition', at_admission)
    def request(payload):
        return health.provider_health(payload, 'offline-forecast42-key', connect_factory=connect)
    night = {'action': 'nightly_claim', 'provider': 'visual_crossing', 'attempt_id': str(uuid4())}
    admitted, status = request(night)
    assert status == 200 and admitted['allowed']
    cycle = {k: admitted['cycle'][k] for k in ('attempt_id', 'cycle_date', 'operating_date')}
    yield connect, request, night, cycle, snapshots, url


def claim(cycle, attempt=None, *, provider='weatherapi'):
    return {'action': 'claim', 'provider': provider, 'attempt_id': attempt or str(uuid4()), 'nightly_cycle': cycle}


def logger_timestamp_after(server_now):
    """Use an actual logger-clock sample after the DB claim, never clamp it.

    Windows clock resolution can briefly lag PostgreSQL by a millisecond.
    This is bounded fixture synchronization, not a production freshness rule.
    """
    deadline = time.monotonic() + 1.0
    while True:
        fetched_at = datetime.now(timezone.utc)
        if fetched_at >= server_now:
            return fetched_at
        if time.monotonic() >= deadline:
            raise AssertionError('forecast fixture clocks did not converge within one second')
        time.sleep(0.002)


def packet_for(pg, provider_claim, generation):
    connect, _, _, cycle, snapshots, _ = pg
    with connect() as db:
        server_now = db.execute('select clock_timestamp()').fetchone()[0].astimezone(timezone.utc)
    # Model the actual logger's post-fetch Python UTC timestamp. A raw DB
    # timestamp can be slightly ahead of the Python ingest-validation clock.
    now = logger_timestamp_after(server_now)
    stamp = now.isoformat()
    provider = provider_claim['provider']
    source = health.SOURCES[provider]
    snapshots.append((source, now))
    return {'provider': provider, 'source_id': source, 'forecast_run_at': stamp,
        'timezone': 'Africa/Johannesburg',
        'provider_health_claim': {'provider': provider, 'attempt_id': provider_claim['attempt_id'], 'generation': generation},
        'provenance': {'provider': provider, 'source_id': source, 'forecast_run_at': stamp,
            'fetched_at': stamp, 'freshness_basis': 'retrieved', 'provider_model_updated_at': None,
            'nightly_cycle': cycle},
        'days': [{'forecast_date': cycle['operating_date'], 'offset_days': 1,
            'temp_max_c': 25, 'temp_min_c': 12, 'rain_sum_mm': 1.2,
            'rain_probability_max_pct': 23, 'wind_max_kmh': 10, 'gust_max_kmh': 33}]}


def read_metadata(connect):
    with connect() as db:
        return dict(db.execute('select source_id,metadata from public.telemetry_sources where source_id=any(%s)',
            ([health.SOURCES['visual_crossing'], health.SOURCES['weatherapi']],)).fetchall())


def final(night, packet):
    return {**night, 'action': 'nightly_result', 'status': 'ingested',
        'source_id': packet['source_id'], 'forecast_run_at': packet['forecast_run_at']}


@pytest.mark.parametrize('same_identity', [True, False])
def test_postgres_claim_recovery_and_competing_identity(recovery_pg, same_identity):
    connect, request, night, cycle, _, _ = recovery_pg
    assert request(night)[0]['status'] == 'nightly_cycle_resumed'
    first = claim(cycle)
    second = deepcopy(first) if same_identity else claim(cycle)
    barrier = Barrier(2)
    def run(payload):
        barrier.wait(timeout=5)
        return request(payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(run, [first, second]))
    assert all(code == 200 for _, code in replies)
    assert sum(reply['allowed'] is True for reply, _ in replies) == (2 if same_identity else 1)
    stored = read_metadata(connect)
    owner = stored[health.SOURCES['visual_crossing']]['forecast_nightly_cycle']
    assert len(owner['attempts']) == 1 and owner['attempts'][0]['generation'] == 1
    if same_identity:
        assert {reply['generation'] for reply, _ in replies} == {1}
    assert request({**night, 'attempt_id': str(uuid4())})[0]['allowed'] is False


@pytest.mark.parametrize('provider', ['weatherapi', 'visual_crossing'])
def test_postgres_ingest_reconciliation_duplicate_result_and_commit_rollback(recovery_pg, monkeypatch, provider):
    from modules.telemetry import weather_service, rootline_cycle_budget
    connect, request, night, cycle, _, url = recovery_pg
    provider_claim = claim(cycle, provider=provider)
    admitted, code = request(provider_claim)
    assert code == 200 and admitted['allowed']
    packet = packet_for(recovery_pg, provider_claim, admitted['generation'])
    body, code = weather_service.ingest_weather_forecast(packet, 'offline-forecast42-key', database_url=url)
    assert code == 201 and body['success'], (code, body)
    before = read_metadata(connect)
    assert before[packet['source_id']]['forecast_provider_health']['status'] == 'pending'
    def expired(**kwargs):
        raise rootline_cycle_budget.RootlineCycleDeadlineExceeded('offline commit margin failure')
    with monkeypatch.context() as patch:
        patch.setattr(rootline_cycle_budget, 'remaining_seconds', expired)
        assert request(final(night, packet))[1] == 503
    assert read_metadata(connect) == before
    barrier = Barrier(2)
    def complete(_):
        barrier.wait(timeout=5)
        return request(final(night, packet))
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(complete, range(2)))
    assert all(code == 200 and reply['success'] for reply, code in replies)
    assert {reply['status'] for reply, _ in replies} == {'nightly_result_recorded', 'nightly_result_replayed'}
    stored = read_metadata(connect)
    assert stored[packet['source_id']]['forecast_provider_health']['status'] == 'ingested'
    owner = stored[health.SOURCES['visual_crossing']]['forecast_nightly_cycle']
    assert owner['status'] == owner['attempts'][0]['status'] == 'ingested'
    assert all(metadata['unrelated'] == 'preserved' for metadata in stored.values())
    with connect() as db:
        assert db.execute('select count(*) from public.weather_forecast_snapshots where source_id=%s and forecast_run_at=%s',
            (packet['source_id'], packet['forecast_run_at'])).fetchone()[0] == 1
    assert request(final(night, packet))[0]['status'] == 'nightly_result_replayed'
    assert read_metadata(connect) == stored


@pytest.mark.parametrize('provider', ['weatherapi', 'visual_crossing'])
def test_postgres_uncommitted_receipt_and_conflicting_result_cannot_finalize(recovery_pg, provider):
    import psycopg
    from modules.telemetry import weather_service
    connect, request, night, cycle, _, url = recovery_pg
    provider_claim = claim(cycle, provider=provider)
    admitted, _ = request(provider_claim)
    packet = packet_for(recovery_pg, provider_claim, admitted['generation'])
    before = read_metadata(connect)
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as db, db.cursor() as cursor:
            health.validate_ingest_claim(cursor, packet)
            cursor.execute('''insert into public.weather_forecast_snapshots
                (forecast_snapshot_id,source_id,forecast_run_at,forecast_date,offset_days)
                values(%s,%s,%s,%s,-1)''',
                ('forecast42-rollback-'+str(uuid4()), packet['source_id'], packet['forecast_run_at'], cycle['operating_date']))
    assert read_metadata(connect) == before
    reply, code = request(final(night, packet))
    assert code == 400 and reply['status'] == 'nightly_cycle_ingest_unproven'
    body, code = weather_service.ingest_weather_forecast(packet, 'offline-forecast42-key', database_url=url)
    assert code == 201 and body['success'], (code, body)
    committed = read_metadata(connect)
    wrong = final(night, packet) | {'forecast_run_at': (datetime.fromisoformat(packet['forecast_run_at'])-timedelta(microseconds=1)).isoformat()}
    assert request(wrong)[1] == 400
    assert read_metadata(connect) == committed
    assert request({**night, 'action': 'nightly_result', 'status': 'failed'})[1] == 400
    assert read_metadata(connect) == committed


def test_packet_clock_is_utc_for_real_ingest_validation(monkeypatch):
    """Offline reproduction of a PostgreSQL session returning a SAST clock."""
    from modules.telemetry import weather_service
    from tests.test_forecast_recovery import Clock, MemoryDatabase, NOW
    monkeypatch.setenv(health.INGEST_API_KEY_ENV, 'offline-forecast42-key')
    monkeypatch.setattr(health, 'datetime', Clock)
    monkeypatch.setattr(sys.modules[__name__], 'datetime', Clock)
    db = MemoryDatabase()
    def endpoint(payload):
        return health.provider_health(payload, 'offline-forecast42-key', connect_factory=lambda: db)
    night = {'action': 'nightly_claim', 'provider': 'visual_crossing', 'attempt_id': str(uuid4())}
    admitted, code = endpoint(night)
    assert code == 200
    cycle = {k: admitted['cycle'][k] for k in ('attempt_id', 'cycle_date', 'operating_date')}
    provider_claim = claim(cycle)
    admitted, code = endpoint(provider_claim)
    assert code == 200
    session_clock = NOW.astimezone(ZoneInfo('Africa/Johannesburg'))
    class SessionClock:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql):
            assert sql == 'select clock_timestamp()'
            return self
        def fetchone(self): return (session_clock,)
    snapshots = []
    packet = packet_for((SessionClock, endpoint, night, cycle, snapshots, None), provider_claim, admitted['generation'])
    assert packet['forecast_run_at'] == NOW.isoformat()
    assert packet['provenance']['fetched_at'] == NOW.isoformat()
    assert snapshots[0][1].utcoffset() == timedelta(0)
    assert weather_service._normalize_forecast_payload(packet)
    assert health.validate_ingest_claim(db, packet)['generation'] == admitted['generation']
    with pytest.raises(ValueError, match='utc_timestamp_required'):
        health._utc(session_clock.isoformat())


def test_fixture_clock_skew_waits_then_uses_actual_python_timestamp(monkeypatch):
    base = datetime(2026, 11, 25, 12, 54, 52, 266316, tzinfo=timezone.utc)
    server_now = base + timedelta(microseconds=1073)
    samples = iter([base, base, base + timedelta(milliseconds=2)])
    captured, sleeps = [], []
    class PythonClock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = next(samples)
            captured.append(value)
            return value
    monkeypatch.setattr(sys.modules[__name__], 'datetime', PythonClock)
    monkeypatch.setattr(time, 'sleep', sleeps.append)
    stamp = logger_timestamp_after(server_now)
    assert sleeps == [0.002, 0.002]
    assert stamp == captured[-1] == base + timedelta(milliseconds=2)
    assert stamp != server_now and stamp.utcoffset() == timedelta(0)


def test_fixture_clock_skew_wait_is_bounded(monkeypatch):
    base = datetime(2026, 11, 25, tzinfo=timezone.utc)
    class StalledClock(datetime):
        @classmethod
        def now(cls, tz=None): return base
    ticks = iter([0.0, 0.5, 1.0])
    sleeps = []
    monkeypatch.setattr(sys.modules[__name__], 'datetime', StalledClock)
    monkeypatch.setattr(time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(time, 'sleep', sleeps.append)
    with pytest.raises(AssertionError, match='within one second'):
        logger_timestamp_after(base + timedelta(milliseconds=1))
    assert sleeps == [0.002]
