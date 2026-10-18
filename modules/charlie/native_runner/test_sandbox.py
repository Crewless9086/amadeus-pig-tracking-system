"""Fail-closed Linux isolation for a fixed, untrusted pytest invocation.

The caller owns the immutable acceptance tests and candidate identity. This
module proves containment, not that arbitrary candidate-controlled tests are
honest. It never fetches packages, accesses providers, or imports candidate
code in the privileged parent.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import errno
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid

SANDBOX_VERSION = "core-linux-tests-v2"
SANDBOX_UID = 65534
MAX_OUTPUT_BYTES = 262144
MAX_COMPLETION_BYTES = 262144
MAX_COLLECTED_TESTS = 1024
MAX_SOURCE_BYTES = 200_000_000
MAX_SOURCE_FILES = 20000
MEMORY_BYTES = 768 * 1024 * 1024
SETUP_EXIT = 125


class SandboxUnavailable(RuntimeError):
    """A safe machine-readable refusal; never includes source or credentials."""


def _path(value):
    path = Path(value).absolute()
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise SandboxUnavailable("sandbox_symlink_path")
    return path.resolve(strict=True)


def _validated_source(source_root, test_paths, scratch_root):
    source, scratch = _path(source_root), _path(scratch_root)
    if not source.is_dir() or not scratch.is_dir():
        raise SandboxUnavailable("sandbox_directory_required")
    if source == scratch or source in scratch.parents or scratch in source.parents:
        raise SandboxUnavailable("sandbox_roots_overlap")
    if source.stat().st_uid != 0 or scratch.stat().st_uid != 0:
        raise SandboxUnavailable("sandbox_root_ownership_required")
    if source.stat().st_mode & 0o022 or scratch.stat().st_mode & 0o022:
        raise SandboxUnavailable("sandbox_root_writable_by_others")
    # The dedicated UID must be able to traverse the staged path. Never chmod
    # the caller's ancestors (which may contain credentials) to achieve this.
    if any(not p.stat().st_mode & 0o001 for p in (scratch, *scratch.parents)):
        raise SandboxUnavailable("sandbox_scratch_ancestor_not_traversable")
    if not isinstance(test_paths, list) or not 1 <= len(test_paths) <= 8:
        raise SandboxUnavailable("sandbox_test_paths_invalid")
    tests = []
    for raw in test_paths:
        if not isinstance(raw, str) or "\\" in raw or ":" in raw:
            raise SandboxUnavailable("sandbox_test_paths_invalid")
        rel = PurePosixPath(raw)
        if (rel.is_absolute() or ".." in rel.parts or rel.as_posix() != raw
                or not raw.startswith("tests/") or not rel.name.startswith("test_")
                or rel.suffix != ".py" or not (source / raw).is_file()):
            raise SandboxUnavailable("sandbox_test_paths_invalid")
        tests.append(raw)
    if len(set(tests)) != len(tests):
        raise SandboxUnavailable("sandbox_test_paths_invalid")
    files, total = [], 0
    for directory, dirs, names in os.walk(source, followlinks=False):
        for name in dirs + names:
            item = Path(directory) / name
            info = item.lstat()
            if (stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
                    or name in {".git", ".charlie_runner", "credentials", "secrets"}
                    or name.startswith(".env") or info.st_uid != 0
                    or info.st_mode & 0o022):
                raise SandboxUnavailable("sandbox_source_entry_forbidden")
            if stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    raise SandboxUnavailable("sandbox_source_hardlink_forbidden")
                files.append(item.relative_to(source))
                total += info.st_size
                if total > MAX_SOURCE_BYTES or len(files) > MAX_SOURCE_FILES:
                    raise SandboxUnavailable("sandbox_source_limit")
    return source, scratch, tests, files


def _stage(source, scratch, files):
    run = Path(tempfile.mkdtemp(prefix="core-tests-", dir=scratch))
    run.chmod(0o755)
    try:
        staged, work = run / "source", run / "work"
        staged.mkdir(mode=0o755)
        work.mkdir(mode=0o700)
        os.chown(work, SANDBOX_UID, SANDBOX_UID)
        for relative in files:
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # A no-follow open protects the final component; root-owned nonwritable
            # ancestors and the admitted immutable copy are required above.
            fd = os.open(source / relative, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            target.chmod(0o444)
        for directory, _, _ in os.walk(staged):
            Path(directory).chmod(0o555)
        return run, staged, work
    except BaseException:
        shutil.rmtree(run)
        raise


def _landlock(read_paths, write_path):
    if platform.machine().lower() not in {"x86_64", "amd64", "aarch64", "arm64"}:
        raise SandboxUnavailable("sandbox_architecture_unsupported")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise SandboxUnavailable("sandbox_landlock_abi_required")
    # ABI 3 covers truncate and cross-directory references. Newer access rights
    # are unnecessary because seccomp rejects device ioctls and networking.
    handled = (1 << 15) - 1
    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]
    class Beneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]
    rules = Ruleset(handled)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise SandboxUnavailable("sandbox_landlock_create_failed")
    read = (1 << 2) | (1 << 3)
    file_bits = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14)
    try:
        for path, access in [*((p, read) for p in read_paths), (write_path, handled & ~(1 << 0))]:
            info = Path(path).stat()
            access = access if stat.S_ISDIR(info.st_mode) else access & file_bits
            node = os.open(path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                rule = Beneath(access, node)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) != 0:
                    raise SandboxUnavailable("sandbox_landlock_rule_failed")
            finally:
                os.close(node)
        if libc.syscall(446, fd, 0) != 0:
            raise SandboxUnavailable("sandbox_landlock_restrict_failed")
    finally:
        os.close(fd)
    return int(abi)


def _seccomp():
    library = ctypes.util.find_library("seccomp")
    if not library:
        raise SandboxUnavailable("sandbox_libseccomp_required")
    lib = ctypes.CDLL(library, use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    # Default deny, including future syscalls and nonnative architectures.
    ctx = lib.seccomp_init(0x00050000 | errno.EPERM)
    if not ctx:
        raise SandboxUnavailable("sandbox_seccomp_create_failed")
    names = """read write readv writev close close_range fcntl fstat newfstatat stat lstat statx
        lseek pread64 pwrite64 open openat readlink readlinkat getdents getdents64 access
        faccessat faccessat2 getcwd chdir fchdir mkdir mkdirat rmdir unlink unlinkat rename
        renameat renameat2 truncate ftruncate fsync fdatasync mmap mmap2 mprotect munmap
        mremap madvise brk rt_sigaction rt_sigprocmask rt_sigreturn sigaltstack clock_gettime
        clock_gettime64 clock_nanosleep clock_nanosleep_time64 nanosleep gettimeofday time
        getpid getppid gettid getuid geteuid getgid getegid getgroups uname getrandom futex
        futex_time64 futex_waitv set_robust_list rseq exit exit_group sysinfo getrusage
        getrlimit poll ppoll ppoll_time64 select pselect6 pselect6_time64 sched_getaffinity
        sched_yield getcpu statfs fstatfs umask restart_syscall""".split()
    try:
        for name in names:
            number = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number >= 0 and lib.seccomp_rule_add(ctx, 0x7FFF0000, number, 0) != 0:
                raise SandboxUnavailable("sandbox_seccomp_rule_failed")
        if lib.seccomp_load(ctx) != 0:
            raise SandboxUnavailable("sandbox_seccomp_load_failed")
    finally:
        lib.seccomp_release(ctx)


class _CompletionRecorder:
    """Trusted pytest observer; it is not an adversarial interpreter boundary."""
    def __init__(self):
        self.collected = None
        self.outcomes = {}
        self.collection_errors = 0
        self.session_exitstatus = None

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report):
        phases = self.outcomes.setdefault(report.nodeid, {})
        if report.when in phases:
            raise RuntimeError("sandbox_duplicate_test_phase")
        phases[report.when] = report.outcome

    def pytest_sessionfinish(self, session, exitstatus):
        self.session_exitstatus = int(exitstatus)

    def receipt(self, nonce, code):
        return {"nonce": nonce, "sandbox_version": SANDBOX_VERSION,
                "completed": self.session_exitstatus == code,
                "exitstatus": code, "collected": self.collected,
                "outcomes": self.outcomes, "collection_errors": self.collection_errors}


def _expected_ids(value, tests):
    if value is None:
        return []
    if (not isinstance(value, list) or not 1 <= len(value) <= MAX_COLLECTED_TESTS
            or any(not isinstance(node, str) or len(node) > 512
                   or not any(node.startswith(path + "::") for path in tests)
                   or "\n" in node or "\r" in node for node in value)
            or len(set(value)) != len(value)):
        raise SandboxUnavailable("sandbox_expected_test_ids_invalid")
    return list(value)


def _verified_completion(raw, nonce, tests, expected, returncode):
    """Validate the bounded observer channel separately from test stdout."""
    try:
        record = json.loads(raw)
        collected, outcomes = record["collected"], record["outcomes"]
        if (set(record) != {"nonce", "sandbox_version", "completed", "exitstatus", "collected",
                            "outcomes", "collection_errors"}
                or record["nonce"] != nonce or record["sandbox_version"] != SANDBOX_VERSION
                or record["completed"] is not True or type(record["exitstatus"]) is not int
                or record["exitstatus"] != returncode or type(record["collection_errors"]) is not int
                or record["collection_errors"] < 0 or not isinstance(collected, list)
                or not 1 <= len(collected) <= MAX_COLLECTED_TESTS
                or any(not isinstance(node, str) or len(node) > 512
                       or not any(node.startswith(path + "::") for path in tests) for node in collected)
                or len(set(collected)) != len(collected) or not set(expected).issubset(collected)
                or not isinstance(outcomes, dict)
                or not set(outcomes).issubset(collected)):
            return {}
        for phases in outcomes.values():
            if (not isinstance(phases, dict) or not set(phases).issubset({"setup", "call", "teardown"})
                    or any(outcome not in {"passed", "failed", "skipped"} for outcome in phases.values())):
                return {}
        passed = {node for node, phases in outcomes.items()
                  if phases == {"setup": "passed", "call": "passed", "teardown": "passed"}}
        return {"verified": True, "completed": True, "collected": collected, "outcomes": outcomes,
                "collection_errors": record["collection_errors"], "exitstatus": returncode,
                "expected_test_ids": expected, "expected_passed": set(expected).issubset(passed),
                "all_passed": set(collected) == passed and record["collection_errors"] == 0}
    except (ValueError, TypeError, KeyError):
        return {}


def _child(config):
    """Trusted launcher installs controls before importing pytest or source."""
    import resource
    ready_fd = int(config["ready_fd"])
    completion_fd = int(config["completion_fd"])
    try:
        timeout = config["timeout"]
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(timeout), math.ceil(timeout) + 1))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_STACK, (16 * 1024 * 1024, 16 * 1024 * 1024))
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise SandboxUnavailable("sandbox_no_new_privs_failed")
        # Resolve loader/library metadata while privileged; no untrusted import.
        library = ctypes.util.find_library("seccomp")
        if not library:
            raise SandboxUnavailable("sandbox_libseccomp_required")
        ctypes.CDLL(library)
        os.setgroups([])
        os.setgid(SANDBOX_UID)
        os.setuid(SANDBOX_UID)
        if os.getuid() != SANDBOX_UID or os.geteuid() != SANDBOX_UID:
            raise SandboxUnavailable("sandbox_uid_drop_failed")
        if libc.prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
            raise SandboxUnavailable("sandbox_dumpability_failed")
        read_paths = {str(Path(sys.executable).resolve()), config["source"]}
        for key in ("stdlib", "platstdlib", "purelib", "platlib"):
            read_paths.add(str(Path(sysconfig.get_path(key)).resolve()))
        for item in ("/lib", "/lib64", "/usr/lib", "/usr/lib64", "/etc/ld.so.cache", "/dev/urandom"):
            if Path(item).exists():
                read_paths.add(str(Path(item).resolve()))
        abi = _landlock(sorted(read_paths), config["work"])
        # find_library can spawn ldconfig; cache the already resolved library
        # name so no discovery command is needed after filesystem confinement.
        original_find = ctypes.util.find_library
        ctypes.util.find_library = lambda name: library if name == "seccomp" else None
        try:
            _seccomp()
        finally:
            ctypes.util.find_library = original_find
        os.chdir(config["source"])
        proof = {"nonce": config["nonce"], "sandbox_version": SANDBOX_VERSION,
                 "landlock_abi": abi, "seccomp": True, "uid": os.getuid(),
                 "network": "denied", "source": "read_only", "writable": "scratch_only",
                 "process_creation": "denied", "resource_limits": True}
        os.write(ready_fd, json.dumps(proof, sort_keys=True).encode() + b"\n")
        os.close(ready_fd)
        ready_fd = -1
        sys.path.insert(0, config["source"])
        import pytest
        recorder = _CompletionRecorder()
        code = pytest.main(["-q", "--capture=no", "-p", "no:cacheprovider", "--confcutdir=" + config["source"],
                            "--basetemp=" + str(Path(config["work"]) / "pytest"),
                            "--log-file=" + str(Path(config["work"]) / "pytest.log"), *config["tests"]],
                           plugins=[recorder])
        # Only the trusted launcher writes completion, after pytest.main returns.
        # Candidate Python shares this interpreter: review and external immutable
        # acceptance tests remain required against deliberate monkeypatching.
        payload = json.dumps(recorder.receipt(config["completion_nonce"], int(code)), sort_keys=True).encode()
        if len(payload) > MAX_COMPLETION_BYTES:
            return SETUP_EXIT
        pending = memoryview(payload)
        while pending:
            written = os.write(completion_fd, pending)
            pending = pending[written:]
        return int(code)
    except BaseException as exc:
        if ready_fd >= 0:
            try:
                os.write(ready_fd, json.dumps({"error": "sandbox_setup_failed", "type": type(exc).__name__}).encode())
            except OSError:
                pass
        if ready_fd < 0:
            sys.stderr.write("sandbox_test_process_failed:" + type(exc).__name__ + "\n")
        return SETUP_EXIT
    finally:
        os.close(completion_fd)
        if ready_fd >= 0:
            os.close(ready_fd)


def run_isolated_tests(source_root: Path, test_paths: list[str], scratch_root: Path, timeout=120,
                       *, expected_test_ids: list[str] | None = None) -> dict:
    if sys.platform != "linux" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise SandboxUnavailable("sandbox_linux_root_controller_required")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 120:
        raise SandboxUnavailable("sandbox_timeout_invalid")
    source, scratch, tests, files = _validated_source(source_root, test_paths, scratch_root)
    expected = _expected_ids(expected_test_ids, tests)
    run, staged, work = _stage(source, scratch, files)
    read_fd, write_fd = os.pipe()
    completion_read, completion_write = os.pipe()
    os.set_inheritable(write_fd, True)
    nonce = uuid.uuid4().hex
    completion_nonce = uuid.uuid4().hex
    config = {"source": str(staged), "work": str(work), "tests": tests,
              "timeout": timeout, "nonce": nonce, "ready_fd": write_fd,
              "completion_fd": completion_write, "completion_nonce": completion_nonce}
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "HOME": str(work), "TMPDIR": str(work), "TMP": str(work), "TEMP": str(work),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "TZ": "UTC"}
    child = None
    output = {"stdout": bytearray(), "stderr": bytearray(), "ready": bytearray(), "completion": bytearray()}
    reason, containment = "", {}
    try:
        child = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                                  "--sandbox-child", json.dumps(config, separators=(",", ":"))],
            cwd=run, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, pass_fds=(write_fd, completion_write), start_new_session=True)
        os.close(write_fd)
        write_fd = -1
        os.close(completion_write)
        completion_write = -1
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for fd, key in ((child.stdout.fileno(), "stdout"), (child.stderr.fileno(), "stderr"), (read_fd, "ready"), (completion_read, "completion")):
                os.set_blocking(fd, False)
                selector.register(fd, selectors.EVENT_READ, key)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "wall_time_limit"
                    break
                for key, _ in selector.select(min(remaining, .1)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fd)
                        continue
                    output[key.data].extend(chunk)
                    if (len(output["stdout"]) + len(output["stderr"]) > MAX_OUTPUT_BYTES
                            or len(output["ready"]) > 4096
                            or len(output["completion"]) > MAX_COMPLETION_BYTES):
                        reason = "output_limit"
                        break
                if reason:
                    break
        if reason:
            os.killpg(child.pid, signal.SIGKILL)
        try:
            child.wait(timeout=5 if reason else max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            reason = "wall_time_limit"
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        try:
            proof = json.loads(output["ready"])
            if (proof.get("nonce") == nonce and proof.get("sandbox_version") == SANDBOX_VERSION
                    and proof.get("landlock_abi", 0) >= 3 and proof.get("seccomp") is True
                    and proof.get("uid") == SANDBOX_UID):
                containment = {k: v for k, v in proof.items() if k != "nonce"}
        except (ValueError, TypeError):
            pass
        if not containment:
            reason = "containment_not_proven"
        completion = _verified_completion(output["completion"], completion_nonce, tests, expected, child.returncode)
        if not reason and not completion:
            reason = "test_completion_not_proven"
        if not reason and child.returncode == 0 and not (completion["all_passed"] and completion["expected_passed"]):
            reason = "tests_not_all_passed"
        return {"returncode": child.returncode if containment and not reason else SETUP_EXIT,
                "stdout": bytes(output["stdout"][:MAX_OUTPUT_BYTES]).decode("utf-8", "replace"),
                "stderr": bytes(output["stderr"][:MAX_OUTPUT_BYTES]).decode("utf-8", "replace"),
                "containment": {"verified": bool(containment), **containment, "termination_reason": reason},
                "completion": completion or {"verified": False, "completed": False},
                "sandbox_version": SANDBOX_VERSION}
    finally:
        if child is not None:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()
        os.close(read_fd)
        os.close(completion_read)
        if completion_write >= 0:
            os.close(completion_write)
        if write_fd >= 0:
            os.close(write_fd)
        # Only this exact freshly owned run directory is removed. Symlinks
        # cannot be created under the filter; rmtree is fd-safe on Linux.
        shutil.rmtree(run)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--sandbox-child":
        raise SystemExit(SETUP_EXIT)
    raise SystemExit(_child(json.loads(sys.argv[2])))
