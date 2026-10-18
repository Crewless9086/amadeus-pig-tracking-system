"""Real Linux containment checks; unsupported hosts prove explicit refusal only."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'modules/charlie/native_runner/test_sandbox.py'
spec = importlib.util.spec_from_file_location('core_test_sandbox', MODULE)
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)
LINUX_ROOT = sys.platform == 'linux' and os.geteuid() == 0


@pytest.fixture
def tree():
    if not LINUX_ROOT:
        pytest.skip('Linux root controller qualification required')
    base = Path(tempfile.mkdtemp(prefix='core-sandbox-qualification-'))
    base.chmod(0o755)
    source, scratch = base / 'input', base / 'runs'
    source.mkdir(mode=0o755)
    scratch.mkdir(mode=0o755)
    (source / 'tests').mkdir(mode=0o755)
    yield source, scratch, base
    shutil.rmtree(base)


def run(tree, content, *, timeout=30, expected_test_ids=None):
    source, scratch, _ = tree
    (source / 'tests/test_probe.py').write_text(content, encoding='utf-8')
    result = sandbox.run_isolated_tests(source, ['tests/test_probe.py'], scratch, timeout,
                                        expected_test_ids=expected_test_ids)
    assert list(scratch.iterdir()) == []
    return result


def test_unsupported_host_refuses_without_subprocess(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox.sys, 'platform', 'win32')
    monkeypatch.setattr(sandbox.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not spawn'))
    with pytest.raises(sandbox.SandboxUnavailable, match='linux_root_controller_required'):
        sandbox.run_isolated_tests(tmp_path, ['tests/test_x.py'], tmp_path)


def test_real_pytest_success_and_failure_are_returned(tree):
    result = run(tree, 'def test_ok():\n    assert 1 + 1 == 2\n')
    assert result['containment']['verified'], result
    assert result['returncode'] == 0, result['stdout'] + result['stderr']
    assert '1 passed' in result['stdout']
    assert result['completion']['verified'] and result['completion']['completed']
    assert result['completion']['collected'] == ['tests/test_probe.py::test_ok']
    assert result['completion']['all_passed']
    result = run(tree, 'def test_bad():\n    assert 1 + 1 == 3\n')
    assert result['returncode'] == 1, result
    assert '1 failed' in result['stdout']
    assert result['completion']['verified'] and result['completion']['completed']
    assert not result['completion']['all_passed']
    assert result['completion']['outcomes']['tests/test_probe.py::test_bad']['call'] == 'failed'


def test_files_network_processes_and_credentials_denied(tree, monkeypatch):
    source, _, base = tree
    secret = base / 'outside-secret'
    secret.write_text('synthetic-secret-never-readable', encoding='utf-8')
    secret.chmod(0o644)  # Landlock must deny even world-readable private input.
    target = base / 'outside-write'
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-do-not-inherit')
    content = '''import os, socket, subprocess, ctypes
from pathlib import Path
import pytest

def test_boundaries():
    assert os.getuid() == 65534
    assert not any('KEY' in k or 'TOKEN' in k or k == 'DATABASE_URL' for k in os.environ)
    for p in (SECRET, '/proc/1/environ', '/proc/self/environ', '/proc/self/mem', '/etc/passwd'):
        with pytest.raises(OSError):
            Path(p).read_bytes()
    for p in (TARGET, __file__):
        with pytest.raises(OSError):
            Path(p).write_text('forbidden')
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        with pytest.raises(OSError):
            socket.socket(family, socket.SOCK_STREAM)
    with pytest.raises(OSError):
        subprocess.run(['/bin/true'], check=True)
    with pytest.raises(OSError):
        os.fork()
    with pytest.raises(OSError):
        os.setuid(0)
    with pytest.raises(OSError):
        os.chmod(__file__, 0o777)
    with pytest.raises(OSError):
        os.symlink(SECRET, os.environ['TMPDIR'] + '/link')
    allowed = Path(os.environ['TMPDIR']) / 'scratch'
    allowed.write_text('allowed')
    assert allowed.read_text() == 'allowed'
'''
    content = 'SECRET=' + repr(str(secret)) + '\nTARGET=' + repr(str(target)) + '\n' + content
    result = run(tree, content)
    assert result['returncode'] == 0, result['stdout'] + result['stderr']
    assert result['containment']['verified'] is True
    assert secret.read_text() == 'synthetic-secret-never-readable'
    assert not target.exists()
    assert (source / 'tests/test_probe.py').read_text() == content
    assert 'synthetic-do-not-inherit' not in result['stdout'] + result['stderr']


def test_wall_time_kills_test_and_preserves_parent(tree):
    result = run(tree, 'import time\ndef test_wait():\n    time.sleep(60)\n', timeout=2)
    assert result['returncode'] == sandbox.SETUP_EXIT
    assert result['containment']['verified'] is True, result
    assert result['containment']['termination_reason'] == 'wall_time_limit'


def test_output_flood_is_bounded(tree):
    result = run(tree, "import os\ndef test_flood():\n    while True: os.write(1, b'x'*65536)\n", timeout=15)
    assert result['returncode'] == sandbox.SETUP_EXIT
    assert result['containment']['termination_reason'] == 'output_limit', result
    assert len(result['stdout'].encode()) <= sandbox.MAX_OUTPUT_BYTES


def test_memory_and_file_size_limits(tree):
    result = run(tree, '''import os
import pytest
from pathlib import Path

def test_memory():
    with pytest.raises(MemoryError):
        bytearray(2 * 1024 * 1024 * 1024)

def test_file_limit():
    with pytest.raises(OSError):
        with (Path(os.environ['TMPDIR']) / 'large').open('wb') as f:
            for _ in range(10): f.write(b'x' * 1024 * 1024)
''')
    assert result['returncode'] == 0, result['stdout'] + result['stderr']


@pytest.mark.parametrize('paths', [[], ['../test_x.py'], ['/tests/test_x.py'], ['tests/test_x.py::test_x'], ['tests/test_x.py', 'tests/test_x.py'], ['tests\\test_x.py']])
def test_test_path_refusals(tree, paths):
    source, scratch, _ = tree
    (source / 'tests/test_x.py').write_text('def test_x(): pass\n')
    with pytest.raises(sandbox.SandboxUnavailable, match='test_paths_invalid'):
        sandbox.run_isolated_tests(source, paths, scratch)
    assert not list(scratch.iterdir())


def test_links_private_paths_and_overlap_refuse_before_launch(tree):
    source, scratch, base = tree
    (source / 'tests/test_x.py').write_text('def test_x(): pass\n')
    private = source / '.env'
    private.write_text('synthetic')
    with pytest.raises(sandbox.SandboxUnavailable, match='source_entry_forbidden'):
        sandbox.run_isolated_tests(source, ['tests/test_x.py'], scratch)
    private.unlink()
    outside = base / 'outside'
    outside.write_text('synthetic')
    link = source / 'linked'
    link.symlink_to(outside)
    with pytest.raises(sandbox.SandboxUnavailable, match='source_entry_forbidden'):
        sandbox.run_isolated_tests(source, ['tests/test_x.py'], scratch)
    link.unlink()
    os.link(outside, link)
    with pytest.raises(sandbox.SandboxUnavailable, match='hardlink_forbidden'):
        sandbox.run_isolated_tests(source, ['tests/test_x.py'], scratch)
    link.unlink()
    with pytest.raises(sandbox.SandboxUnavailable, match='roots_overlap'):
        sandbox.run_isolated_tests(source, ['tests/test_x.py'], source)


def test_unknown_syscalls_and_process_memory_denied(tree):
    result = run(tree, '''import ctypes, errno, os

def test_kernel_boundaries():
    c=ctypes.CDLL(None, use_errno=True)
    # Linux common/x86_64: ptrace, unshare, bpf, userfaultfd, io_uring_setup.
    import platform
    if platform.machine() != 'x86_64': return
    for nr in (101, 272, 321, 323, 425, 999999):
        ctypes.set_errno(0)
        assert c.syscall(nr, 0, 0, 0, 0, 0, 0) == -1
        assert ctypes.get_errno() == errno.EPERM
''')
    assert result['returncode'] == 0, result['stdout'] + result['stderr']


def test_closed_output_cannot_escape_wall_deadline(tree):
    import time
    started = time.monotonic()
    result = run(tree, 'import os, time\ndef test_close():\n    os.close(1)\n    os.close(2)\n    time.sleep(60)\n', timeout=2)
    assert time.monotonic() - started < 6
    assert result['returncode'] == sandbox.SETUP_EXIT
    assert result['containment']['termination_reason'] == 'wall_time_limit'


def test_missing_seccomp_library_fails_closed(monkeypatch):
    monkeypatch.setattr(sandbox.ctypes.util, 'find_library', lambda _: None)
    with pytest.raises(sandbox.SandboxUnavailable, match='libseccomp_required'):
        sandbox._seccomp()


def test_staging_failure_cleans_exact_owned_directory(tree, monkeypatch):
    source, scratch, _ = tree
    f = source / 'tests/test_x.py'
    f.write_text('def test_x(): pass\n')
    monkeypatch.setattr(sandbox.shutil, 'copyfileobj', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic')))
    with pytest.raises(OSError):
        sandbox._stage(source, scratch, [Path('tests/test_x.py')])
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize('content', [
    'import os; os._exit(0)\n',
    'import os\ndef test_exit(): os._exit(0)\n',
    '# no collected tests\n',
])
def test_abrupt_exit_and_empty_collection_never_pass(tree, content):
    result = run(tree, content)
    assert result['returncode'] == sandbox.SETUP_EXIT, result
    assert result['containment']['verified']
    assert result['containment']['termination_reason'] == 'test_completion_not_proven'
    assert result['completion'] == {'verified': False, 'completed': False}


@pytest.mark.parametrize('content', [
    'import pytest\ndef test_skip(): pytest.skip("synthetic")\n',
    'import pytest\n@pytest.mark.xfail(reason="synthetic")\ndef test_xfail(): assert False\n',
])
def test_skipped_test_success_code_is_refused(tree, content):
    result = run(tree, content)
    assert result['returncode'] == sandbox.SETUP_EXIT, result
    assert result['completion']['verified'] and result['completion']['completed']
    assert not result['completion']['all_passed']
    assert result['containment']['termination_reason'] == 'tests_not_all_passed'


def test_expected_acceptance_id_must_be_collected_and_pass(tree):
    node = 'tests/test_probe.py::test_acceptance'
    result = run(tree, 'def test_acceptance(): assert True\n', expected_test_ids=[node])
    assert result['returncode'] == 0, result
    assert result['completion']['expected_test_ids'] == [node]
    assert result['completion']['expected_passed']
    result = run(tree, 'def test_acceptance(): assert False\n', expected_test_ids=[node])
    assert result['returncode'] == 1, result
    assert result['completion']['verified'] and not result['completion']['expected_passed']
    result = run(tree, 'def test_other(): assert True\n', expected_test_ids=[node])
    assert result['returncode'] == sandbox.SETUP_EXIT, result
    assert not result['completion']['verified']


def test_completion_channel_rejects_forged_stdout_and_collection_errors(tree):
    result = run(tree, 'import os\ndef test_exit():\n    print("{\\"completed\\":true}", flush=True)\n    os._exit(0)\n')
    assert result['returncode'] == sandbox.SETUP_EXIT
    assert not result['completion']['verified']
    result = run(tree, 'import missing_sandbox_module\ndef test_unreachable(): pass\n')
    assert result['returncode'] == sandbox.SETUP_EXIT
    assert not result['completion']['verified']


def test_completion_receipt_nonce_and_schema_fail_closed():
    import json
    record = {'nonce': 'correct', 'sandbox_version': sandbox.SANDBOX_VERSION,
              'completed': True, 'exitstatus': 0, 'collected': ['tests/test_probe.py::test_ok'],
              'outcomes': {'tests/test_probe.py::test_ok': {'setup': 'passed', 'call': 'passed', 'teardown': 'passed'}},
              'collection_errors': 0}
    assert sandbox._verified_completion(json.dumps(record), 'correct', ['tests/test_probe.py'], [], 0)['all_passed']
    assert sandbox._verified_completion(json.dumps(record), 'wrong', ['tests/test_probe.py'], [], 0) == {}
    assert sandbox._verified_completion(json.dumps(record), 'correct', ['tests/test_probe.py'], [], 1) == {}
    record['outcomes']['tests/test_probe.py::test_ok']['call'] = 'skipped'
    assert not sandbox._verified_completion(json.dumps(record), 'correct', ['tests/test_probe.py'], [], 0)['all_passed']


def test_expected_id_validation_precedes_staging(tree):
    source, scratch, _ = tree
    (source / 'tests/test_probe.py').write_text('def test_ok(): pass\n')
    for ids in ([], ['elsewhere.py::test_x'], ['tests/test_probe.py::x'] * 2, [42]):
        with pytest.raises(sandbox.SandboxUnavailable, match='expected_test_ids_invalid'):
            sandbox.run_isolated_tests(source, ['tests/test_probe.py'], scratch, expected_test_ids=ids)
    assert list(scratch.iterdir()) == []
