import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PYTHON_MODULES = ("psycopg", "reportlab")


def resolve_python_executable(repo_root=None):
    root = Path(repo_root or REPO_ROOT).resolve()
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
    ]
    for parent in root.parents:
        candidates.extend([
            parent / ".venv" / "Scripts" / "python.exe",
            parent / "venv" / "Scripts" / "python.exe",
        ])
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def python_test_command(args="", repo_root=None):
    executable = resolve_python_executable(repo_root=repo_root)
    suffix = str(args or "").strip()
    quoted = _quote_command_part(executable)
    return f"{quoted} {suffix}".strip()


def runner_environment_preflight(repo_root=None, require_browser=False):
    root = Path(repo_root or REPO_ROOT).resolve()
    python_executable = resolve_python_executable(root)
    python_exists = Path(python_executable).exists()
    missing_modules = _missing_modules_for_python(python_executable) if python_exists else list(REQUIRED_PYTHON_MODULES)
    browser = _browser_preflight(root) if require_browser else {"required": False, "available": None, "reason": "not_required"}
    success = python_exists and not missing_modules and (not require_browser or browser.get("available") is True)
    return {
        "success": success,
        "status": "runner_preflight_passed" if success else "runner_preflight_failed",
        "repo_root": str(root),
        "python_executable": python_executable,
        "python_exists": python_exists,
        "required_python_modules": list(REQUIRED_PYTHON_MODULES),
        "missing_python_modules": missing_modules,
        "browser": browser,
        "recommended_action": _recommended_action(python_exists, missing_modules, browser, require_browser),
    }


def _browser_preflight(repo_root):
    node_modules_playwright = _resolve_playwright_command(repo_root)
    if not node_modules_playwright.exists():
        return {
            "required": True,
            "available": False,
            "reason": "playwright_cmd_missing",
            "path": str(node_modules_playwright),
        }
    try:
        completed = subprocess.run(
            [str(node_modules_playwright), "--version"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "required": True,
            "available": False,
            "reason": f"playwright_probe_failed:{exc.__class__.__name__}",
            "path": str(node_modules_playwright),
        }
    return {
        "required": True,
        "available": completed.returncode == 0,
        "reason": "playwright_available" if completed.returncode == 0 else "playwright_version_failed",
        "path": str(node_modules_playwright),
        "stdout": (completed.stdout or "").strip()[:200],
        "stderr": (completed.stderr or "").strip()[:200],
    }


def _resolve_playwright_command(repo_root):
    executable_names = ("playwright.cmd", "playwright.exe") if sys.platform.startswith("win") else ("playwright",)
    roots = [repo_root, *repo_root.parents]
    for root in roots:
        for name in executable_names:
            candidate = root / "node_modules" / ".bin" / name
            if candidate.exists():
                return candidate
    return repo_root / "node_modules" / ".bin" / executable_names[0]


def _missing_modules_for_python(python_executable):
    missing = []
    for module_name in REQUIRED_PYTHON_MODULES:
        try:
            completed = subprocess.run(
                [python_executable, "-c", f"import {module_name}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            missing.append(module_name)
            continue
        if completed.returncode != 0:
            missing.append(module_name)
    return missing


def _recommended_action(python_exists, missing_modules, browser, require_browser):
    if not python_exists:
        return "Restore the project venv or start the runner with a Python executable that has repo dependencies installed."
    if missing_modules:
        return "Install missing runner dependencies in the Python environment: " + ", ".join(missing_modules)
    if require_browser and browser.get("available") is not True:
        return "Install/restore Playwright browser tooling before running UI missions."
    return "Runner environment is ready."


def _quote_command_part(value):
    text = str(value or "")
    if not text:
        return text
    if any(char.isspace() for char in text):
        return f'"{text}"'
    return text
