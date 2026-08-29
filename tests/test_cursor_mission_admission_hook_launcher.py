import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / ".cursor" / "hooks" / "charlie_mission_admission_guard.cjs"


def _node(script):
    return subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False
    )


def test_hooks_use_portable_node_launcher_only():
    hooks = json.loads((ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    commands = [item["command"] for stage in hooks["hooks"].values() for item in stage]
    assert all(command.startswith("node .cursor/hooks/charlie_mission_admission_guard.cjs hook") for command in commands)
    assert not any(command.startswith("python ") for command in commands)
    assert all(item["failClosed"] is True for stage in hooks["hooks"].values() for item in stage)


def test_interpreter_order_is_platform_specific():
    result = _node(
        f"const m=require({json.dumps(str(LAUNCHER))});"
        "console.log(JSON.stringify({linux:m.interpreterCandidates('linux'),win:m.interpreterCandidates('win32')}));"
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["linux"] == [["python3", []], ["python", []], ["py", ["-3"]]]
    assert value["win"] == [["python", []], ["py", ["-3"]], ["python3", []]]


def test_missing_interpreter_falls_back_and_preserves_io_and_success():
    script = f"""
const m=require({json.dumps(str(LAUNCHER))});
const calls=[];
const code=m.runGuard({{
  input:Buffer.from('exact-input'), platform:'linux',
  spawn:(exe,args,opts)=>{{ calls.push([exe,args,opts.shell,opts.input.toString()]);
    if(exe==='python3') return {{error:Object.assign(new Error('missing'),{{code:'ENOENT'}})}};
    return {{status:0,stdout:Buffer.from('guard-out'),stderr:Buffer.from('guard-err')}};
  }}
}});
process.stderr.write('\\nRESULT '+JSON.stringify({{code,calls}}));
"""
    result = _node(script)
    assert result.returncode == 0
    assert result.stdout == "guard-out"
    marker = json.loads(result.stderr.split("RESULT ", 1)[1])
    assert marker["code"] == 0
    assert [call[0] for call in marker["calls"]] == ["python3", "python"]
    assert marker["calls"][1][2:] == [False, "exact-input"]
    assert "guard-err" in result.stderr


def test_guard_denial_is_exact_and_never_retries():
    script = f"""
const m=require({json.dumps(str(LAUNCHER))}); let count=0;
const code=m.runGuard({{input:Buffer.from('x'),platform:'win32',spawn:()=>{{count++;return {{status:2,stdout:Buffer.alloc(0),stderr:Buffer.alloc(0)}};}}}});
console.log(JSON.stringify({{code,count}}));
"""
    result = _node(script)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"code": 2, "count": 1}


def test_windows_python_is_first_and_missing_all_fails_closed():
    script = f"""
const m=require({json.dumps(str(LAUNCHER))}); const calls=[];
const code=m.runGuard({{input:Buffer.alloc(0),platform:'win32',spawn:(exe)=>{{calls.push(exe);return {{error:Object.assign(new Error('missing'),{{code:'ENOENT'}})}};}}}});
console.log(JSON.stringify({{code,calls}}));
"""
    result = _node(script)
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value == {"code": 127, "calls": ["python", "py", "python3"]}
    assert "no supported Python interpreter" in result.stderr


def test_launcher_has_no_shell_execution():
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "shell: false" in source
    assert "shell: true" not in source


def test_separate_node_launcher_invocations_share_one_oidc_mint():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        hooks, scripts = root / ".cursor" / "hooks", root / "scripts"
        (root / "runtime").mkdir()
        hooks.mkdir(parents=True)
        scripts.mkdir()
        copied_launcher = hooks / LAUNCHER.name
        shutil.copyfile(LAUNCHER, copied_launcher)
        counter = root / "mint-count.txt"
        (scripts / "charlie_mission_admission_guard.py").write_text(r'''
import os, time
import scripts.charlie_mission_admission_guard as guard
guard._cursor_cloud_socket = lambda env: env["CURSOR_AGENT_SOCKET"]
class Response:
    status = 200
    def read(self, limit):
        return ("{\"token\":\"node-shared-test-token\",\"expires_at\":%d}" % (int(time.time()) + 300)).encode()
    def getheader(self, name): return None
class Connection:
    def __init__(self, path, timeout=None): pass
    def request(self, *args, **kwargs):
        path = os.environ["CHARLIE_TEST_MINT_COUNTER"]
        current = int(open(path).read() or "0") if os.path.exists(path) else 0
        with open(path, "w") as handle: handle.write(str(current + 1))
    def getresponse(self): return Response()
    def close(self): pass
token = guard._mint_cursor_oidc(os.environ, connection_factory=Connection)
raise SystemExit(0 if token == "node-shared-test-token" else 3)
''', encoding="utf-8")
        environment = dict(os.environ)
        environment.update({"XDG_RUNTIME_DIR": str(root / "runtime"),
                            "CURSOR_AGENT_SOCKET": "/run/cursor/node-test.sock",
                            "CHARLIE_TEST_MINT_COUNTER": str(counter),
                            "PYTHONPATH": str(ROOT)})
        processes = [subprocess.Popen(["node", str(copied_launcher), "hook"], cwd=root,
                     env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True) for _ in range(12)]
        results = [process.communicate("{}", timeout=20) + (process.returncode,)
                   for process in processes]
        assert all(result[2] == 0 for result in results), results
        assert counter.read_text(encoding="utf-8") == "1"
