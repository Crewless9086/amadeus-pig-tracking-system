"""Local startup contracts. Real image phase tests live in the mission receipt."""
import importlib
import json
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import charlie_render_native_runner as bootstrap
from scripts import charlie_native_runner as native


class StartupShutdownTests(unittest.TestCase):
    def handlers(self):
        return {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}

    def test_import_does_not_replace_handlers(self):
        before = self.handlers()
        importlib.reload(bootstrap)
        importlib.reload(native)
        self.assertEqual(self.handlers(), before)

    def test_failed_exec_restores_handlers_and_mask(self):
        before = self.handlers()
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, set()) if hasattr(signal, 'pthread_sigmask') else None
        def fail(*args):
            if mask is not None:
                self.assertTrue({signal.SIGTERM, signal.SIGINT} <= signal.pthread_sigmask(signal.SIG_BLOCK, set()))
            raise OSError('synthetic exec failure')
        with patch.object(bootstrap, 'prepare_hermes_profile'), patch.object(bootstrap, 'prepare_repository'), patch.object(bootstrap.os, 'execvpe', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'synthetic'):
                bootstrap.main()
        self.assertEqual(self.handlers(), before)
        if mask is not None:
            self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, set()), mask)

    def test_interrupted_profile_preserves_old_file_and_unrelated_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp)
            old = b'{"auxiliary":{"transient_retries":4},"retained":true}'
            (profile / 'config.yaml').write_bytes(old)
            (profile / 'config.tmp').write_bytes(b'unrelated retained work')
            (profile / 'hold.json').write_bytes(b'BLOCKED_HOLD')
            with patch.object(bootstrap, 'PROFILE', profile), patch.object(bootstrap.os, 'replace', side_effect=SystemExit(143)):
                with self.assertRaises(SystemExit):
                    bootstrap.prepare_hermes_profile()
            self.assertEqual((profile / 'config.yaml').read_bytes(), old)
            self.assertEqual((profile / 'config.tmp').read_bytes(), b'unrelated retained work')
            self.assertEqual((profile / 'hold.json').read_bytes(), b'BLOCKED_HOLD')
            pending = list(profile.glob('.config-*.tmp'))
            self.assertEqual(len(pending), 1)
            self.assertEqual(json.loads(pending[0].read_text())['auxiliary']['transient_retries'], 0)
            with patch.object(bootstrap, 'PROFILE', profile):
                bootstrap.prepare_hermes_profile()
            self.assertTrue(pending[0].exists())
            self.assertEqual(json.loads((profile / 'config.yaml').read_text())['retained'], True)

    def test_rejected_git_exit_remains_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError):
            bootstrap.run([os.sys.executable, '-c', 'raise SystemExit(7)'])

    def test_git_timeout_is_bounded(self):
        with patch.object(bootstrap, 'GIT_TIMEOUT_SECONDS', .05):
            with self.assertRaises(subprocess.TimeoutExpired):
                bootstrap.run([os.sys.executable, '-c', 'import time;time.sleep(10)'])

    def test_successful_child_retains_output(self):
        result = bootstrap.run([os.sys.executable, '-c', 'print("synthetic")'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'synthetic')

    def test_constructor_signal_has_no_watch_or_once_effect(self):
        before = self.handlers()
        effects = []
        def construct(**kwargs):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            effects.append('constructed')
        fake = SimpleNamespace(NativeRunnerService=construct)
        with patch.dict('sys.modules', {'modules.charlie.native_runner.service': fake}):
            with self.assertRaises(SystemExit) as raised:
                native.main(['--watch', '--profile-home', 'synthetic', '--repository-root', 'synthetic', '--worktree-root', 'synthetic'])
        self.assertEqual(raised.exception.code, 143)
        self.assertEqual(effects, [])
        self.assertEqual(self.handlers(), before)

    def test_ready_watch_receives_stop_without_execution(self):
        effects = []
        def watch(interval, stop_event):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            self.assertTrue(stop_event.is_set())
            effects.append('watch-stop')
            return 0
        fake = SimpleNamespace(NativeRunnerService=lambda **kw: SimpleNamespace(watch=watch))
        with patch.dict('sys.modules', {'modules.charlie.native_runner.service': fake}):
            self.assertEqual(native.main(['--watch', '--profile-home', 'synthetic', '--repository-root', 'synthetic', '--worktree-root', 'synthetic']), 0)
        self.assertEqual(effects, ['watch-stop'])


if __name__ == '__main__':
    unittest.main()
