from datetime import date

from modules.pig_weights.pig_weights_service import _purpose_review_eligibility


def growth(days, *, wean=date(2026, 8, 1), weight=None):
    return {"days_since_wean": days, "wean_date": wean, "latest_weight_date": weight}


def test_day_13_is_quiet_and_day_14_without_post_wean_weight_is_one_weight_gate():
    assert _purpose_review_eligibility(growth(13), "Unknown") == {
        "state": "quiet", "eligible": False,
    }
    assert _purpose_review_eligibility(growth(14), "Unknown") == {
        "state": "weight_due", "eligible": True,
    }


def test_day_14_with_post_wean_weight_is_decision_due():
    assert _purpose_review_eligibility(
        growth(14, weight=date(2026, 8, 8)), "Unknown",
    ) == {"state": "decision_due", "eligible": True}


def test_resolved_purpose_removes_eligibility():
    assert _purpose_review_eligibility(
        growth(14, weight=date(2026, 8, 8)), "Breeding",
    ) == {"state": "resolved", "eligible": False}
