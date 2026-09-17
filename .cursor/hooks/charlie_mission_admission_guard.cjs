"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function interpreterCandidates(platform = process.platform) {
  return platform === "win32"
    ? [["python", []], ["py", ["-3"]], ["python3", []]]
    : [["python3", []], ["python", []], ["py", ["-3"]]];
}

function repositoryRoot(launcherFile = __filename) {
  return path.resolve(path.dirname(launcherFile), "..", "..");
}

function runGuard({
  input = fs.readFileSync(0),
  args = process.argv.slice(2),
  platform = process.platform,
  spawn = spawnSync,
  launcherFile = __filename,
  env = process.env,
} = {}) {
  const root = repositoryRoot(launcherFile);
  const guard = path.join(root, "scripts", "charlie_mission_admission_guard.py");
  for (const [executable, prefix] of interpreterCandidates(platform)) {
    const result = spawn(executable, [...prefix, guard, ...args], {
      cwd: root,
      env,
      input,
      encoding: null,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });
    if (result.error && result.error.code === "ENOENT") continue;
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    if (result.error) {
      process.stderr.write("CHARLIE admission guard launcher failed closed.\n");
      return 127;
    }
    return Number.isInteger(result.status) ? result.status : 1;
  }
  process.stderr.write("CHARLIE admission guard launcher: no supported Python interpreter.\n");
  return 127;
}

module.exports = { interpreterCandidates, repositoryRoot, runGuard };

if (require.main === module) process.exitCode = runGuard();
