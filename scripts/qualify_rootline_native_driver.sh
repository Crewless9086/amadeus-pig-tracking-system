#!/usr/bin/env bash
# CI-only qualification; no production connection or effect.
set -euo pipefail
probe_env="$RUNNER_TEMP/rootline-$ROOTLINE_PROBE-venv"
probe_evidence="$RUNNER_TEMP/rootline-driver-evidence/$ROOTLINE_PROBE"
mkdir -p "$probe_evidence"
python -m venv "$probe_env"
export ROOTLINE_PROBE_EVIDENCE="$probe_evidence"
"$probe_env/bin/python" -B - <<'PY'
import os
from pathlib import Path
source_path = Path('requirements.txt')
source_bytes = source_path.read_bytes()
source = source_bytes.decode().splitlines()
needle = 'psycopg[binary]>=3.2,<4'
assert source.count(needle) == 1, 'review changed dependency input before continuing'
v = os.environ['ROOTLINE_DRIVER']
probe = os.environ['ROOTLINE_PROBE']
assert (probe, v) in {('production_tuple', '3.3.7'), ('minimum_driver', '3.2.0')}
out = Path(os.environ['ROOTLINE_PROBE_EVIDENCE'])
(out/'constraints.txt').write_text('psycopg=='+v+'\npsycopg-binary=='+v+'\n')
if probe == 'production_tuple':
    (out/'requirements.txt').write_bytes(source_bytes)
else:
    lines = []
    for line in source:
        lines.extend(['psycopg==3.2.0', 'psycopg-binary==3.2.0'] if line == needle else [line])
    (out/'requirements.txt').write_text('\n'.join(lines)+'\n')
assert source_path.read_bytes() == source_bytes
PY
"$probe_env/bin/python" -m pip install --only-binary=psycopg,psycopg-binary \
  --report "$probe_evidence/install.json" -r "$probe_evidence/requirements.txt" \
  -c "$probe_evidence/constraints.txt" pytest openai==2.24.0 httpx==0.28.1
"$probe_env/bin/python" -m pip check
"$probe_env/bin/python" -B - <<'PY'
import hashlib, importlib.metadata as metadata, json, os, platform, subprocess, sys
from pathlib import Path
import psycopg, psycopg_binary.pq, pytest
out = Path(os.environ['ROOTLINE_PROBE_EVIDENCE'])
files = ['tests/test_rootline_no_send_preparation_postgres.py',
         'tests/test_rootline_no_send_pair_postgres.py',
         'tests/test_rootline_eligibility_read_scope_postgres.py']
sources = files + ['tests/test_rootline_final_bc_snapshot.py',
  'tests/test_rootline_eligibility_read_scope.py',
  'tests/test_rootline_managed_optional_noop.py',
  'modules/telemetry/rootline_managed_devices_runtime.py',
  'modules/telemetry/rootline_execution_runtime.py',
  'modules/oom_sakkie/bounded_postgres_read.py',
  'modules/sales/sam_live_stock_launch_control.py',
  *['modules/telemetry/'+name+'.py' for name in (
    'rootline_ewelink_oauth_store','rootline_ewelink_readback',
    'rootline_ewelink_request_budget','rootline_ifttt_transport',
    'rootline_irrigation_coordinator','rootline_irrigation_execution_store')]]
before = {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
revision = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
record = dict(revision=revision, python=platform.python_version(),
  implementation=platform.python_implementation(), executable=sys.executable,
  system=platform.system(), machine=platform.machine(), libc=platform.libc_ver(),
  psycopg=psycopg.__version__, distribution=metadata.version('psycopg'),
  binary_distribution=metadata.version('psycopg-binary'), pq_impl=psycopg.pq.__impl__,
  libpq=psycopg.pq.version(), binary_path=psycopg_binary.pq.__file__,
  binary_sha256=hashlib.sha256(Path(psycopg_binary.pq.__file__).read_bytes()).hexdigest(),
  pytest=metadata.version('pytest'),
  source_sha256=before)
(out/'versions.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,sort_keys=True))
assert revision == os.environ['ROOTLINE_EXPECTED_REVISION']
assert record['system']=='Linux' and record['implementation']=='CPython'
expected_python=os.environ['ROOTLINE_PYTHON']
assert (record['python']==expected_python if expected_python=='3.14.3'
        else tuple(sys.version_info[:2])==(3,12))
assert record['psycopg']==record['distribution']==record['binary_distribution']==os.environ['ROOTLINE_DRIVER']
assert record['pq_impl']=='binary'
if os.environ['ROOTLINE_LIBPQ']:
    assert record['libpq']==int(os.environ['ROOTLINE_LIBPQ']), 'production libpq tuple not reproduced'
assert os.environ['ROOTLINE_DISPOSABLE_POSTGRES_URL']==os.environ['DATABASE_URL']
assert os.environ['DATABASE_URL']=='postgresql://postgres:postgres@127.0.0.1:5432/rootline_no_send_test'
class Coverage:
    def __init__(self): self.nodes=[]; self.deselected=[]; self.skipped=[]; self.xfail=[]
    def pytest_collection_finish(self, session): self.nodes=[item.nodeid for item in session.items]
    def pytest_deselected(self, items): self.deselected.extend(item.nodeid for item in items)
    def pytest_runtest_logreport(self, report):
        if report.skipped: self.skipped.append(report.nodeid)
        if hasattr(report,'wasxfail'): self.xfail.append(report.nodeid)
coverage=Coverage()
result=pytest.main(['-q','-ra','-p','no:cacheprovider','-o','addopts=',
  '--junitxml='+str(out/'results.xml'),*files], plugins=[coverage])
seen={node.split('::')[0] for node in coverage.nodes}
after = {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
report=dict(source_unchanged=before==after, after_sha256=after, exit_code=int(result),nodeids=coverage.nodes,deselected=coverage.deselected,
            skipped=coverage.skipped,xfail_or_xpass=coverage.xfail)
(out/'coverage.json').write_text(json.dumps(report,indent=2)+'\n')
assert before==after
assert result==0 and seen==set(files) and coverage.nodes
assert not coverage.deselected and not coverage.skipped and not coverage.xfail
PY
