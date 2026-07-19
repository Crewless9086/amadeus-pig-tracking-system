
"""Process-wide safety boundary for CHARLIE unit tests.

This package is imported before any ``tests.test_charlie_*`` module.  Establish
an isolated control root here so module-level CHARLIE paths can never resolve to
the owner's live ``.charlie_runner`` directory.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path


os.environ["CHARLIE_TEST_ISOLATION"] = "1"
_configured_root = str(os.environ.get("CHARLIE_TEST_CONTROL_ROOT") or "").strip()
_created_control_root = not bool(_configured_root)
if _created_control_root:
    _configured_root = tempfile.mkdtemp(prefix="charlie-unit-control-")
os.environ["CHARLIE_TEST_CONTROL_ROOT"] = _configured_root
os.environ.pop("CHARLIE_PROCESS_TERMINATION_ENABLED", None)
os.environ.pop("CHARLIE_SUBPROCESS_TESTS_ENABLED", None)

from modules.charlie import validated_test_control_root


_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTROL_ROOT = validated_test_control_root(_REPO_ROOT)
os.environ["CHARLIE_TEST_CONTROL_ROOT"] = str(_CONTROL_ROOT)


def _cleanup_created_control_root():
    if not _created_control_root:
        return
    resolved = _CONTROL_ROOT.resolve()
    temp_parent = Path(tempfile.gettempdir()).resolve()
    if resolved.parent != temp_parent or not resolved.name.startswith("charlie-unit-control-"):
        return
    shutil.rmtree(resolved, ignore_errors=True)


atexit.register(_cleanup_created_control_root)


def isolated_control_root():
    return _CONTROL_ROOT
