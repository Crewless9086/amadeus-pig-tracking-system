"""Production-shaped HTTP/state-machine recovery, without external services.

Memory transactions here test protocol paths, not PostgreSQL locking proof.
The separately guarded PostgreSQL cases exercise the same paths on real rows.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from modules.telemetry import forecast_provider_health as health
from tests.test_forecast_logger import forecast_logger as logger, backup_fixture

NOW = datetime(2026, 11, 19, 21, 31, tzinfo=timezone.utc)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class MemoryDatabase:
    def __init__(self):
        self.rows = {source: ({'unrelated': 'preserved'}, provider, 'forecast', True)
            for provider, source in health.SOURCES.items()}
        self.writes = []
        self.last = None

    def __enter__(self):
        self.before = deepcopy(self.rows)
        return self

    def __exit__(self, kind, error, traceback):
        if kind:
            self.rows = self.before

    def cursor(self):
        # The real connection and cursor own nested scopes. This cursor has no
        # transaction ownership, so only the outer connection rolls back.
        from contextlib import nullcontext
        return nullcontext(self)

    def execute(self, sql, params=None):
        self.last = (sql, params)
        if 'update public.telemetry_sources' in sql:
            key = 'forecast_nightly_cycle' if '{forecast_nightly_cycle}' in sql else 'forecast_provider_health'
            self.rows[params[1]][0][key] = json.loads(params[0])
            self.writes.append((params[1], key))
        return self

    def fetchone(self):
        sql, params = self.last
        return (NOW,) if sql == 'select clock_timestamp()' else deepcopy(self.rows.get(params[0]))

    @property
    def cycle(self):
        return self.rows[health.SOURCES['visual_crossing']][0]['forecast_nightly_cycle']


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV, 'offline-key')
    monkeypatch.setattr(health, 'datetime', Clock)
    monkeypatch.setattr(logger, 'datetime', Clock)
    monkeypatch.setattr(logger, 'AMADEUS_BACKEND_URL', 'https://offline.invalid')
    monkeypatch.setattr(logger, 'TELEMETRY_INGEST_API_KEY', 'offline-key')
    monkeypatch.setattr(logger.time, 'sleep', lambda _: None)
    db = MemoryDatabase()
    requests = []

    def endpoint(url, *, json, headers, timeout):
        requests.append(deepcopy(json))
        body, code = health.provider_health(json, headers['X-Amadeus-Telemetry-Key'], connect_factory=lambda: db)
        return type('Response', (), {'status_code': code, 'json': lambda self: body})()

    monkeypatch.setattr(logger.requests, 'post', endpoint)
    return db, requests, endpoint


def admit(db, provider='weatherapi'):
    night = {'action': 'nightly_claim', 'provider': 'visual_crossing', 'attempt_id': str(uuid4())}
    reply = logger._health_request(night)
    cycle = {k: reply['cycle'][k] for k in ('attempt_id', 'cycle_date', 'operating_date')}
    request = {'action': 'claim', 'provider': provider, 'attempt_id': str(uuid4()), 'nightly_cycle': cycle}
    provider_reply = logger._health_request(request)
    claim = {k: request[k] for k in ('provider', 'attempt_id')} | {'generation': provider_reply['generation']}
    packet = {'provider': provider, 'source_id': health.SOURCES[provider], 'forecast_run_at': NOW.isoformat(),
        'provenance': {'nightly_cycle': cycle}, 'provider_health_claim': claim}
    return night, request, packet


def final(night, packet):
    return {**night, 'action': 'nightly_result', 'status': 'ingested',
        'source_id': packet['source_id'], 'forecast_run_at': packet['forecast_run_at']}


@pytest.mark.parametrize('action', ['nightly_claim', 'claim'])
def test_lost_claim_response_resumes_exact_identity_without_new_generation(protocol, monkeypatch, action):
    db, sent, endpoint = protocol
    lost = []
    def lose_once(url, **kwargs):
        reply = endpoint(url, **kwargs)
        if kwargs['json']['action'] == action and not lost:
            lost.append(True)
            raise logger.requests.Timeout('response lost after commit')
        return reply
    monkeypatch.setattr(logger.requests, 'post', lose_once)
    night, request, packet = admit(db)
    matching = [r for r in sent if r['action'] == action]
    assert len(matching) == 2 and len({r['attempt_id'] for r in matching}) == 1
    assert len(db.cycle['attempts']) == 1 and db.cycle['attempts'][0]['generation'] == 1
    competitor = {**request, 'attempt_id': str(uuid4())}
    assert logger._health_request(competitor)['allowed'] is False
    assert logger._health_request({**night, 'attempt_id': str(uuid4())})['allowed'] is False


def test_pending_claim_resume_does_not_extend_lease_or_revive_old_cycle(protocol):
    db, _, _ = protocol
    night, request, packet = admit(db)
    before = deepcopy(db.rows)
    assert logger._health_request(request)['allowed']
    assert db.rows == before
    state = db.rows[packet['source_id']][0]['forecast_provider_health']
    assert health.transition(state, {k:v for k,v in request.items() if k != 'nightly_cycle'},
        NOW + timedelta(minutes=16))[1]['allowed'] is False
    assert health.nightly_transition(db.cycle, night, NOW + timedelta(days=1))[1]['allowed'] is False


@pytest.mark.parametrize('lose_result', [False, True])
def test_committed_backup_ingest_reconciles_and_replays_atomically(protocol, monkeypatch, lose_result):
    db, sent, endpoint = protocol
    night, request, packet = admit(db)
    with db:
        health.validate_ingest_claim(db, packet)
    assert db.cycle['attempts'][0]['status'] == 'pending'
    lost = []
    def lose_once(url, **kwargs):
        reply = endpoint(url, **kwargs)
        if lose_result and kwargs['json']['action'] == 'nightly_result' and not lost:
            lost.append(True)
            raise logger.requests.Timeout('result response lost after commit')
        return reply
    monkeypatch.setattr(logger.requests, 'post', lose_once)
    assert logger._health_request(final(night, packet))['success']
    assert db.cycle['status'] == 'ingested' and db.cycle['attempts'][0]['status'] == 'ingested'
    assert db.rows[packet['source_id']][0]['forecast_provider_health']['status'] == 'ingested'
    assert all(row[0]['unrelated'] == 'preserved' for row in db.rows.values())
    writes = len(db.writes)
    assert logger._health_request(final(night, packet))['status'] == 'nightly_result_replayed'
    assert len(db.writes) == writes


@pytest.mark.parametrize('change', ['generation', 'source', 'run', 'attempt', 'failed_cycle'])
def test_reconciliation_rejects_mismatched_or_historical_evidence(protocol, change):
    db, _, _ = protocol
    night, request, packet = admit(db)
    with db:
        health.validate_ingest_claim(db, packet)
    if change == 'generation':
        db.cycle['ingest']['generation'] += 1
    elif change == 'source':
        db.cycle['ingest']['source_id'] = health.SOURCES['open_meteo']
    elif change == 'run':
        packet['forecast_run_at'] = (NOW - timedelta(seconds=1)).isoformat()
    elif change == 'attempt':
        db.rows[packet['source_id']][0]['forecast_provider_health']['attempt_id'] = str(uuid4())
    else:
        db.cycle['status'] = 'failed'
        db.cycle['result'] = {'status': 'failed', 'source_id': None, 'forecast_run_at': None}
    before = deepcopy(db.rows)
    with pytest.raises(logger.ForecastHealthError):
        logger._health_request(final(night, packet))
    assert db.rows == before


def test_receipt_rollback_cannot_finalize_and_committed_receipt_cannot_fail(protocol):
    db, _, _ = protocol
    night, request, packet = admit(db)
    with pytest.raises(ValueError, match='snapshot insert failed'):
        with db:
            health.validate_ingest_claim(db, packet)
            raise ValueError('snapshot insert failed')
    with pytest.raises(logger.ForecastHealthError) as error:
        logger._health_request(final(night, packet))
    assert error.value.status == 'nightly_cycle_ingest_unproven'
    with db:
        health.validate_ingest_claim(db, packet)
    before = deepcopy(db.rows)
    with pytest.raises(logger.ForecastHealthError):
        logger._health_request({**night, 'action': 'nightly_result', 'status': 'failed'})
    assert db.rows == before


def test_expiry_retry_and_transport_exhaustion_keep_payload_identity(protocol, monkeypatch):
    db, sent, endpoint = protocol
    clock = [0.0]
    monkeypatch.setattr(logger.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(logger.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    attempts = []
    def unavailable(url, **kwargs):
        attempts.append(deepcopy(kwargs))
        clock[0] += 48
        raise logger.requests.Timeout('offline')
    monkeypatch.setattr(logger.requests, 'post', unavailable)
    request = {'action': 'nightly_claim', 'provider': 'visual_crossing', 'attempt_id': str(uuid4())}
    with pytest.raises(logger.ForecastHealthError, match='unavailable'):
        logger._health_request(request)
    assert len(attempts) == 3 and clock[0] <= logger.HEALTH_OPERATION_SECONDS
    assert all({k:v for k,v in a['json'].items() if k != 'request_expires_at'} == request for a in attempts)
    assert all(a['timeout'][0] == 3 and a['timeout'][1] <= 48 for a in attempts)
    assert not db.writes


def test_http_expiry_retries_without_expired_request_database_access(protocol, monkeypatch):
    db, _, endpoint = protocol
    seen = []
    def expire_first(url, **kwargs):
        if not seen:
            seen.append(deepcopy(kwargs['json']))
            expired = {**kwargs['json'], 'request_expires_at': (NOW-timedelta(seconds=1)).isoformat()}
            def forbidden():
                raise AssertionError('expired request must not connect')
            body, code = health.provider_health(expired, 'offline-key', connect_factory=forbidden)
            assert code == 408 and not db.writes
            return type('Response', (), {'status_code': code, 'json': lambda self: body})()
        assert kwargs['json']['attempt_id'] == seen[0]['attempt_id']
        return endpoint(url, **kwargs)
    monkeypatch.setattr(logger.requests, 'post', expire_first)
    assert logger._health_request({'action': 'nightly_claim', 'provider': 'visual_crossing',
        'attempt_id': str(uuid4())})['allowed']


def test_lost_provider_result_response_replays_without_new_result(protocol, monkeypatch):
    db, _, endpoint = protocol
    night, request, packet = admit(db)
    with db:
        health.validate_ingest_claim(db, packet)
    lost = []
    def lose_once(url, **kwargs):
        reply = endpoint(url, **kwargs)
        if not lost:
            lost.append(True)
            raise logger.requests.Timeout('response lost after provider result commit')
        return reply
    monkeypatch.setattr(logger.requests, 'post', lose_once)
    report = {**request, 'action': 'result', 'generation': 1, 'status': 'ingested',
        'failure_kind': None, 'retry_not_before': None, 'forecast_run_at': packet['forecast_run_at']}
    assert logger._health_request(report)['replayed']
    assert db.cycle['attempts'][0]['status'] == 'ingested'
    assert db.cycle['status'] == 'pending'
    assert logger._health_request(final(night, packet))['success']


@pytest.mark.parametrize('lost_ingest_ack', [False, True])
@pytest.mark.parametrize('completion_available', [False, True])
def test_main_backup_journey_recovers_result_or_ingest_ack_loss(protocol, monkeypatch, capsys, lost_ingest_ack, completion_available):
    db, sent, endpoint = protocol
    monkeypatch.setenv('LAT', '-34')
    monkeypatch.setenv('LON', '21')
    monkeypatch.setenv('TIMEZONE', 'Africa/Johannesburg')
    monkeypatch.setenv('FORECAST_PROVIDERS', 'visual_crossing,weatherapi')
    monkeypatch.setenv('WEATHERAPI_API_KEY', 'offline')
    monkeypatch.setattr(logger, 'refresh_configuration', lambda: None)
    monkeypatch.setattr(logger, 'load_dotenv', lambda: None)
    monkeypatch.setattr(logger, 'BACKEND_INGEST_ENABLED', True)
    monkeypatch.setattr(logger, 'GOOGLE_SHEETS_ENABLED', False)
    def primary(**kwargs):
        raise RuntimeError('primary unavailable')
    monkeypatch.setattr(logger, 'fetch_visual_crossing_daily', primary)
    monkeypatch.setattr(logger, 'fetch_weatherapi_daily', lambda **kwargs: backup_fixture())
    def ingest(packet):
        with db:
            health.validate_ingest_claim(db, packet)
        return (False, 'Timeout') if lost_ingest_ack else (True, None)
    monkeypatch.setattr(logger, 'post_backend_ingest', ingest)
    def health_transport(url, **kwargs):
        if kwargs['json'].get('action') == 'nightly_result' and not completion_available:
            raise logger.requests.Timeout('completion unavailable')
        if kwargs['json'].get('action') == 'result' and kwargs['json'].get('provider') == 'weatherapi':
            raise logger.requests.Timeout('provider result request lost')
        return endpoint(url, **kwargs)
    monkeypatch.setattr(logger.requests, 'post', health_transport)
    if completion_available:
        logger.main()
    else:
        with pytest.raises(SystemExit) as error:
            logger.main()
        assert error.value.code == 3
    summary = json.loads(capsys.readouterr().out)
    assert summary['success'] is completion_available
    assert summary['nightly_result_confirmed'] is completion_available
    assert summary['backend_ingest_success'] is (not lost_ingest_ack)
    assert db.cycle['status'] == ('ingested' if completion_available else 'pending')
    assert [a['status'] for a in db.cycle['attempts']] == ['fetch_failed', 'ingested' if completion_available else 'pending']
    assert not any(r.get('action') == 'nightly_result' and r.get('status') == 'failed' for r in sent)
