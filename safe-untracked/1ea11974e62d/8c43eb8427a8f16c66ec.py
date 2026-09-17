"""The external-candidate wire contract, derived from canonical authority."""
import re

from .execution import NativeExecutionError, normalize_repo_path

LIST_FIELDS = ("changed_files", "allowed_files", "forbidden_files", "allowed_effects",
               "forbidden_effects", "required_tests", "operational_acceptance")
FIELDS = frozenset(("pr_number", "branch_name", "base_sha", "head_sha",
                    "candidate_diff_sha256", "generation", *LIST_FIELDS))
PROGRESS_FIELDS = ("pr_number", "head_sha", "changed_files", "candidate_diff_sha256")


def validate_binding(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise NativeExecutionError("native_candidate_contract_incomplete")
    if (type(value["pr_number"]) is not int or value["pr_number"] <= 0
            or any(not isinstance(value[k], str) or not value[k].strip()
                   or value[k] != value[k].strip() for k in ("branch_name", "generation"))
            or any(not re.fullmatch(r"[0-9a-f]{40}", str(value[k])) for k in ("base_sha", "head_sha"))
            or not re.fullmatch(r"[0-9a-f]{64}", str(value["candidate_diff_sha256"]))):
        raise NativeExecutionError("native_candidate_contract_invalid")
    for key in LIST_FIELDS:
        if (not isinstance(value[key], list) or not value[key]
                or any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in value[key])
                or len(value[key]) != len(set(value[key]))):
            raise NativeExecutionError("native_candidate_contract_invalid")
    result = {**value, **{key: sorted(value[key]) for key in LIST_FIELDS}}
    for path in result["allowed_files"] + result["changed_files"]:
        if normalize_repo_path(path) != path:
            raise NativeExecutionError("native_candidate_scope_invalid")
    if result["changed_files"] != result["allowed_files"]:
        raise NativeExecutionError("native_candidate_scope_mismatch")
    return result


def canonical_projection(binding):
    value = validate_binding(binding)
    packet = {"pr_number": value["pr_number"], "branch_name": value["branch_name"],
              "candidate_revision": value["head_sha"], "candidate_diff_sha256": value["candidate_diff_sha256"],
              "changed_files": value["changed_files"]}
    contract = {"generation": value["generation"], "branch": value["branch_name"], "base_sha": value["base_sha"],
                **{k: value[k] for k in LIST_FIELDS if k != "changed_files"}}
    return packet, contract


def binding_from_authority(mission, native):
    """Never substitute builder output or generic tests for the canonical vault."""
    if native.get("mission_id") != mission.get("mission_id"):
        raise NativeExecutionError("native_candidate_mission_mismatch")
    metadata = mission.get("metadata") or {}
    vault = mission.get("vault") or metadata.get("mission_vault") or {}
    tests, acceptance = vault.get("test_plan"), vault.get("acceptance_criteria")
    existing = metadata.get("mission_admission_contract") or {}
    # An already bound contract is the frozen source on restart/correction.
    if existing:
        tests, acceptance = existing.get("required_tests"), existing.get("operational_acceptance")
    binding = validate_binding({
        "pr_number": native.get("pr_number"), "branch_name": native.get("branch"),
        "base_sha": native.get("starting_main_sha"), "head_sha": native.get("head_sha"),
        "candidate_diff_sha256": native.get("candidate_diff_sha256"),
        "changed_files": native.get("changed_files"), "generation": native.get("generation"),
        **{k: native.get(k) for k in ("allowed_files", "forbidden_files", "allowed_effects", "forbidden_effects")},
        "required_tests": tests, "operational_acceptance": acceptance,
    })
    if native.get("base_sha", binding["base_sha"]) != binding["base_sha"]:
        raise NativeExecutionError("native_candidate_base_mismatch")
    if existing and canonical_projection(binding)[1] != existing:
        raise NativeExecutionError("native_candidate_authority_mismatch")
    return binding


def progress_candidate(candidate):
    """Immutable base and branch belong to native authorization, not progress."""
    return {key: candidate[key] for key in PROGRESS_FIELDS}
