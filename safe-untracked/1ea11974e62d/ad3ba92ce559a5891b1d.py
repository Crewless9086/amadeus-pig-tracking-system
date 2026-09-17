"""Dependency-root regressions; real installed checks use an explicit image gate."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load(ROOT / 'deploy/charlie-native-runner/verify_dependency_contract.py', 'dependency_contract_under_test')
bootstrap = load(ROOT / 'scripts/charlie_render_native_runner.py', 'dependency_bootstrap_under_test')


def pkg(version, requires=None):
    return {'version': version, 'requires': requires or []}


class DependencyContractTests(unittest.TestCase):
    def test_known_sequential_install_conflicts_are_both_rejected(self):
        # Exact conflicting versions from the retained audited installation.
        rows = check.evaluate(['python-dotenv==1.0.1', 'cryptography>=43,<46'],
                              {'python-dotenv': pkg('1.2.2'), 'cryptography': pkg('50.0.0')})
        self.assertEqual([row['satisfied'] for row in rows], [False, False])

    def test_missing_distribution_is_rejected(self):
        self.assertFalse(check.evaluate(['Flask==3.0.3'], {})[0]['satisfied'])

    def test_conflicting_exact_version_is_rejected(self):
        self.assertFalse(check.evaluate(['python-dotenv==1.0.1'], {'python-dotenv': pkg('1.2.2')})[0]['satisfied'])

    def test_satisfied_version_range_is_accepted(self):
        self.assertTrue(check.evaluate(['cryptography>=43,<46'], {'cryptography': pkg('45.0.7')})[0]['satisfied'])

    def test_selected_extra_dependency_is_required(self):
        rows = check.evaluate(['httpx[socks]==0.28.1'], {'httpx': pkg('0.28.1', ['socksio==1.0.0; extra == "socks"'])})
        self.assertTrue(any(row['requirement'].startswith('socksio') and not row['satisfied'] for row in rows))

    def test_unselected_extra_is_not_required(self):
        rows = check.evaluate(['httpx==0.28.1'], {'httpx': pkg('0.28.1', ['socksio==1.0.0; extra == "socks"'])})
        self.assertEqual(len(rows), 1)

    def test_transitive_conflict_is_rejected(self):
        rows = check.evaluate(['outer==1'], {'outer': pkg('1', ['inner<2']), 'inner': pkg('2')})
        self.assertFalse(all(row['satisfied'] for row in rows))

    def test_linux_marker_does_not_require_windows_distribution(self):
        self.assertEqual(check.evaluate(['pywin32==311; sys_platform == "win32"'], {}, {'sys_platform': 'linux'}), [])

    def test_dependency_cycle_is_bounded(self):
        rows = check.evaluate(['a==1'], {'a': pkg('1', ['b==1']), 'b': pkg('1', ['a==1'])})
        self.assertEqual(len(rows), 2)

    def test_bootstrap_selects_hermes_and_preserves_application_path(self):
        seen = {}
        def execute(executable, argv, env):
            seen.update(executable=executable, argv=list(argv), path=env['PATH'])
        with patch.dict(os.environ, {'PYTHON': '/opt/hermes-venv/bin/python', 'PATH': '/usr/local/bin:/usr/bin:/bin'}, clear=True), \
                patch.object(bootstrap, 'prepare_repository') as repository, \
                patch.object(bootstrap, 'prepare_hermes_profile') as profile, \
                patch.object(bootstrap.os, 'execvpe', side_effect=execute):
            bootstrap.main()
        repository.assert_called_once()
        profile.assert_called_once()
        self.assertEqual(seen['executable'], '/opt/hermes-venv/bin/python')
        self.assertEqual(seen['argv'][:3], ['/opt/hermes-venv/bin/python', '-m', 'scripts.charlie_native_runner'])
        self.assertEqual(seen['path'], '/usr/local/bin:/usr/bin:/bin')

    def test_profile_update_retains_configuration_and_hold(self):
        with tempfile.TemporaryDirectory(prefix='charlie-dependency-profile-') as temp:
            root = Path(temp)
            profile = root / 'profile'
            profile.mkdir()
            (profile / 'config.yaml').write_text(json.dumps({'auxiliary': {'transient_retries': 4}, 'owner_context': 'synthetic-preserved'}))
            hold = root / '.runner-status.json'
            hold.write_bytes(b'{"state":"BLOCKED_HOLD","fingerprint":"synthetic"}')
            original = hold.read_bytes()
            with patch.object(bootstrap, 'PROFILE', profile):
                bootstrap.prepare_hermes_profile()
            self.assertEqual(hold.read_bytes(), original)
            self.assertEqual(json.loads((profile / 'config.yaml').read_text()), {'auxiliary': {'transient_retries': 0}, 'owner_context': 'synthetic-preserved'})

    def test_main_rejects_same_environment_even_when_requirements_match(self):
        with tempfile.TemporaryDirectory(prefix='charlie-dependency-main-') as temp:
            root = Path(temp)
            (root / 'requirements.txt').write_text('python-dotenv==1.0.1\n')
            (root / 'pyproject.toml').write_text('[project]\nversion="1"\ndependencies=["python-dotenv==1.0.1"]\n')
            inventory = {'prefix': '/one', 'base_prefix': '/one', 'packages': {'hermes-agent': pkg('1'), 'python-dotenv': pkg('1.0.1')}}
            with patch.object(check, 'inventory', return_value=inventory), contextlib.redirect_stdout(io.StringIO()) as output:
                result = check.main(['--application-python', 'fake-app', '--hermes-python', 'fake-hermes',
                                     '--application-requirements', str(root / 'requirements.txt'), '--hermes-project', str(root / 'pyproject.toml')])
            self.assertEqual(result, 1)
            self.assertFalse(json.loads(output.getvalue())['satisfied'])


@unittest.skipUnless(os.environ.get('CHARLIE_IMAGE_CONTRACT_TEST') == '1', 'requires the owned built image; no host/provider fallback')
class InstalledDependencyContractTests(unittest.TestCase):
    def test_actual_interpreter_inventories_and_main(self):
        app = check.inventory('/usr/local/bin/python')
        hermes = check.inventory('/opt/hermes-venv/bin/python')
        self.assertEqual(app['prefix'], '/usr/local')
        self.assertEqual(hermes['prefix'], '/opt/hermes-venv')
        app_packages = {check.canonicalize_name(k): v for k, v in app['packages'].items()}
        hermes_packages = {check.canonicalize_name(k): v for k, v in hermes['packages'].items()}
        self.assertEqual(app_packages['python-dotenv']['version'], '1.0.1')
        self.assertEqual(hermes_packages['python-dotenv']['version'], '1.2.2')
        self.assertEqual(hermes_packages['cryptography']['version'], '50.0.0')
        self.assertNotIn('hermes-agent', app_packages)
        self.assertNotIn('flask', hermes_packages)
        self.assertNotIn('psycopg', hermes_packages)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = check.main(['--application-python', '/usr/local/bin/python', '--hermes-python', '/opt/hermes-venv/bin/python',
                                 '--application-requirements', str(ROOT / 'requirements.txt'), '--hermes-project', '/opt/hermes-agent/pyproject.toml'])
        self.assertEqual(result, 0, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())['satisfied'])


if __name__ == '__main__':
    unittest.main()
