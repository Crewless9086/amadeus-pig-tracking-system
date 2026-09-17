"""Disposable cross-process test plane; actual full app under application Python.

This helper is inert unless explicitly started by the isolated image harness.
Only provider transport and the synthetic issuer public key are substituted.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request


class RemoteClient:
    def __init__(self, port, cookie=''):
        self.port, self.cookie = port, cookie

    def open(self, path, method='GET', headers=None, data=None, json=None):
        import json as codec
        from types import SimpleNamespace
        headers = dict(headers or {})
        if self.cookie:
            headers['Cookie'] = 'session=' + self.cookie
        if json is not None:
            data = codec.dumps(json).encode()
            headers['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            value = codec.loads(response.read())
            return SimpleNamespace(status_code=response.status, json=value, get_json=lambda: value)
        finally:
            connection.close()

    def post(self, path, **kwargs):
        return self.open(path, method='POST', **kwargs)

    def get(self, path, **kwargs):
        return self.open(path, **kwargs)


def start_plane(tmp_path, settings, dsn, callback, cookie):
    """Start an owned application child; no live URLs or inherited credentials."""
    from tests.test_charlie_native_image_roles import disposable_role_dsn
    assert os.environ.get('CHARLIE_TEST_SPLIT_APPLICATION_PLANE') == '1'
    assert dsn.startswith('host=127.0.0.1 ') and 'user=native_recovery_test ' in dsn
    class ProviderCallback(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            request = urllib.request.Request(payload['url'], data=payload['body'].encode() if payload['body'] is not None else None,
                                             headers=payload['headers'], method=payload['method'])
            try:
                with callback(request) as result:
                    body, status = result.read(), result.status
            except urllib.error.HTTPError as error:
                body, status = error.read(), error.code
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), ProviderCallback)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ready = tmp_path / 'application-ready.json'
    key = tmp_path / 'synthetic-issuer-public-key.txt'
    env = {'PATH': os.environ['PATH'], 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1',
           'CHARLIE_TEST_ISOLATION': '1', 'CHARLIE_TEST_CONTROL_ROOT': str(tmp_path / 'control'),
           'DATABASE_URL': disposable_role_dsn(dsn,'service_role'),
           'CHARLIE_MISSION_DATABASE_URL': disposable_role_dsn(dsn,'charlie_mission_application'),
           'QUALIFICATION_CALLBACK_PORT': str(server.server_port), 'QUALIFICATION_READY': str(ready),
           'QUALIFICATION_ISSUER_KEY': str(key), **settings}
    log = (tmp_path / 'application-plane.log').open('w')
    process = subprocess.Popen(['/usr/local/bin/python', str(Path(__file__).resolve()), '--application-plane'],
                               cwd=Path(__file__).resolve().parents[1], env=env, stdout=log, stderr=log)
    try:
        for _ in range(150):
            if ready.exists():
                identity = json.loads(ready.read_text())
                assert identity['prefix'] == '/usr/local' and identity['full_app'] is True
                return {'owner': RemoteClient(identity['port'], cookie), 'worker': RemoteClient(identity['port']),
                        'process': process, 'server': server, 'thread': thread, 'log': log, 'key': key, 'identity': identity}
            if process.poll() is not None:
                raise RuntimeError('application plane failed: ' + (tmp_path / 'application-plane.log').read_text())
            time.sleep(.1)
        raise RuntimeError('application plane readiness timeout')
    except BaseException:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close();log.close()
        raise


def stop_plane(plane):
    plane['process'].terminate()
    plane['process'].wait(timeout=10)
    plane['server'].shutdown()
    plane['server'].server_close()
    plane['thread'].join(timeout=5)
    plane['log'].close()


def application_main():
    assert os.environ.get('CHARLIE_TEST_ISOLATION') == '1'
    assert os.environ['DATABASE_URL'].startswith('host=127.0.0.1 ')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    callback_port = int(os.environ['QUALIFICATION_CALLBACK_PORT'])
    calls = []
    def provider(request, timeout=30):
        assert hasattr(request, 'full_url')
        assert not request.full_url.startswith('https://canonical.test/')
        body = json.dumps({'url': request.full_url, 'method': request.get_method(),
                           'headers': dict(request.header_items()), 'body': request.data.decode() if request.data else None})
        calls.append({'url': request.full_url, 'method': request.get_method(), 'transport': 'labelled fake callback'})
        connection = http.client.HTTPConnection('127.0.0.1', callback_port, timeout=timeout)
        try:
            connection.request('POST', '/', body=body, headers={'Content-Type': 'application/json'})
            response = connection.getresponse();data = response.read()
            if response.status >= 400:
                raise urllib.error.HTTPError(request.full_url, response.status, 'synthetic provider result', {}, io.BytesIO(data))
            value = io.BytesIO(data);value.status = response.status
            return value
        finally:
            connection.close()
    urllib.request.urlopen = provider
    # Existing runtime starts are disabled by the clean synthetic environment.
    # Detect any accidental startup-thread attempt before starting our test HTTP server.
    original_start = threading.Thread.start
    def denied_start(*args, **kwargs):
        raise RuntimeError('unexpected application background startup')
    threading.Thread.start = denied_start
    import app
    threading.Thread.start = original_start
    assert 'charlie' in app.app.blueprints
    from scripts import charlie_mission_admission_guard as guard
    @app.app.before_request
    def synthetic_issuer_fixture():
        path = Path(os.environ['QUALIFICATION_ISSUER_KEY'])
        if path.exists():
            guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64 = path.read_text()
    from werkzeug.serving import make_server
    # The labelled fake issuer calls back synchronously while the admission
    # request is open. Allow that separate real HTTP request to complete.
    server = make_server('127.0.0.1', 0, app.app, threaded=True)
    import importlib.metadata as metadata
    from modules.charlie import mission_store
    with mission_store._connect(os.environ['CHARLIE_MISSION_DATABASE_URL']) as connection:
        database_identity = connection.execute('select session_user,current_user').fetchone()
    assert database_identity == ('charlie_mission_application','charlie_mission_application')
    identity = {'executable': sys.executable, 'prefix': sys.prefix, 'pid': os.getpid(), 'port': server.server_port,
                'full_app': True, 'database_role': database_identity[1], 'database_session_user': database_identity[0], 'provider_transport': 'labelled fake callback',
                'packages': {p: metadata.version(p) for p in ['Flask', 'python-dotenv', 'cryptography', 'psycopg']}}
    Path(os.environ['QUALIFICATION_READY']).write_text(json.dumps(identity, indent=2))
    server.serve_forever()


if __name__ == '__main__':
    assert sys.argv[1:] == ['--application-plane']
    application_main()
