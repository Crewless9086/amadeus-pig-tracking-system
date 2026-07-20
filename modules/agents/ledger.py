"""Ledger Operational V1: read-only commercial evidence validation."""

from datetime import datetime, timezone

from modules.charlie.agent_runtime import AgentDefinition


LEDGER_DEFINITION = AgentDefinition(
    agent_id="ledger", name="Ledger", domain="finance", authority_tier="read_only",
    capabilities=("livestock_price_evidence", "commercial_review"),
    source_contract=("Supabase sales_pricing", "verified order totals"),
    handler=lambda request: run_ledger(request),
)


def run_ledger(request):
    request = request if isinstance(request, dict) else {}
    context = request.get("known_context") if isinstance(request.get("known_context"), dict) else {}
    pricing = context.get("pricing") if isinstance(context.get("pricing"), dict) else {}
    payment = context.get("payment") if isinstance(context.get("payment"), dict) else {}
    found = bool(pricing.get("found") and pricing.get("unit_price") not in (None, ""))
    payment_status = str(payment.get("status") or "unknown").strip().lower()
    if payment_status not in {"unknown", "unverified", "verified", "not_required"}:
        payment_status = "unknown"
    direct = (
        f"Ledger verified {pricing.get('currency') or 'ZAR'} {pricing.get('unit_price')} per animal from {pricing.get('source') or 'the active price book'}."
        if found else "Ledger could not verify an active livestock price for the requested category and weight band."
    )
    return {
        "success": True, "status": "ledger_price_evidence_ready", "capability": "livestock_price_evidence",
        "direct_answer": direct, "facts": [
            {"name": "price_verified", "value": found},
            {"name": "payment_status", "value": payment_status},
        ],
        "metrics": {"unit_price": pricing.get("unit_price") if found else None}, "breakdown": {}, "anomalies": [], "inferences": [],
        "recommendations": [] if found else ["Keep the reply at owner review until the price book resolves."],
        "unresolved_questions": (
            ([] if found else ["Active price rule is missing."])
            + (["Canonical payment evidence was not supplied."] if payment_status in {"unknown", "unverified"} else [])
        ),
        "sources": [{"name": pricing.get("source") or "sales_pricing", "authority": "commercial price evidence"}],
        "freshness": {"observed_at": datetime.now(timezone.utc).isoformat(), "mode": "current_decision_evidence"},
        "confidence": 0.99 if found else 0.82, "summary": direct, "pricing": pricing,
        "payment": {
            "status": payment_status,
            "evidence_supplied": bool(payment),
            # Ledger only reports commercial evidence. A caller-provided status,
            # including "verified", cannot grant a payment or livestock-release
            # authority that belongs to the owner-gated backend rail.
            "payment_confirmation_allowed": False,
            "authority_note": "Ledger evidence never authorizes payment confirmation or livestock release.",
        },
    }
