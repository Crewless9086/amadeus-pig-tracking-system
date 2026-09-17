"""Exact candidate acceptance, separate from execution and owner release."""
import re
from .execution import NativeExecutionError
from .canonical_client import GitHubObserver


def validate_acceptance(native, observed):
    expected = {"pr_number": native.get("pr_number"), "base_sha": native.get("starting_main_sha"),
                "head_sha": native.get("head_sha"), "candidate_diff_sha256": native.get("candidate_diff_sha256"),
                "changed_files": native.get("changed_files")}
    if (not re.fullmatch(r"[0-9a-f]{40}", str(expected["head_sha"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(expected["candidate_diff_sha256"]))
            or observed.get("head_sha") != expected["head_sha"] or observed.get("pr_number") != expected["pr_number"]
            or observed.get("draft") is not True or observed.get("all_required_checks_pass") is not True
            or set(observed.get("checks") or {}) != GitHubObserver.REQUIRED
            or any(v != "success" for v in observed["checks"].values())):
        raise NativeExecutionError("native_acceptance_checks_unproven")
    identities = set()
    for role in ("security", "functional"):
        review = native.get("review_" + role) or {}
        if (review.get("verdict") != "APPROVE" or review.get("candidate_binding") != expected
                or review.get("reviewer_task") != "charlie_native_" + role + "_reviewer"
                or not re.fullmatch(r"[0-9a-f]{64}", str(review.get("packet_sha256")))
                or not str(review.get("reviewer_identity", "")).startswith("HNR-")
                or review["reviewer_identity"] == native.get("builder_identity")
                or review["reviewer_identity"] in identities):
            raise NativeExecutionError("native_acceptance_review_unproven")
        identities.add(review["reviewer_identity"])
    if type(native.get("correction_rounds")) is not int or native["correction_rounds"] < 1:
        raise NativeExecutionError("native_acceptance_correction_unproven")
    return expected
