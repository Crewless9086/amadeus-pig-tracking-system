"""Verify both source dependency contracts after the complete image installation."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tomllib

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def inventory(python):
    code = (
        "import importlib.metadata as m,json,sys; "
        "print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,"
        "base_prefix=sys.base_prefix,packages={d.metadata['Name']:"
        "dict(version=d.version,requires=d.requires or []) for d in m.distributions()})))"
    )
    return json.loads(subprocess.check_output([python, "-I", "-c", code], text=True))


def evaluate(requirements, packages, environment=None):
    """Check roots and their selected extra dependencies, never optional extras wholesale."""
    packages = {canonicalize_name(name): value for name, value in packages.items()}
    environment = environment or default_environment()
    pending = [(text, "") for text in requirements]
    seen = set()
    rows = []
    while pending:
        text, extra = pending.pop(0)
        if (text, extra) in seen:
            continue
        seen.add((text, extra))
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate({**environment, "extra": extra}):
            continue
        installed = packages.get(canonicalize_name(requirement.name))
        version = installed["version"] if installed else None
        valid = bool(installed and requirement.specifier.contains(version))
        rows.append({"requirement": text, "extra": extra, "installed": version, "satisfied": valid})
        if installed:
            for child in installed.get("requires", []):
                pending.extend((child, selected) for selected in {"", *requirement.extras})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-python", required=True)
    parser.add_argument("--hermes-python", required=True)
    parser.add_argument("--application-requirements", required=True)
    parser.add_argument("--hermes-project", required=True)
    args = parser.parse_args(argv)
    app = inventory(args.application_python)
    hermes = inventory(args.hermes_python)
    project = tomllib.loads(Path(args.hermes_project).read_text())["project"]
    roots = [line.strip() for line in Path(args.application_requirements).read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    separated = (app["prefix"] != hermes["prefix"]
                 and hermes["prefix"] != hermes["base_prefix"])
    app_rows = evaluate(roots, app["packages"])
    hermes_rows = evaluate(["hermes-agent==" + project["version"], *project["dependencies"]], hermes["packages"])
    report = {"separate_interpreters": separated, "application": app_rows, "hermes": hermes_rows}
    report["satisfied"] = separated and all(row["satisfied"] for row in app_rows + hermes_rows)
    print(json.dumps(report, indent=2))
    return 0 if report["satisfied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
