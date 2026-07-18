"""Governed capability discovery for Charl's private executive."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class ExecutiveCapability:
    intent_type: str
    domain: str
    authority_tier: str
    source_of_truth: str
    keywords: tuple[str, ...]
    description: str
    follow_ups: tuple[str, ...] = ()
    freshness_seconds: int = 300
    required_args: tuple[str, ...] = ()


CAPABILITIES = (
    ExecutiveCapability("read_core_status", "engineering", "auto", "Supabase charlie_missions + runner heartbeat", ("core", "runner", "active", "running", "progress", "overnight"), "Read current CORE and runner truth.", ("read_blocked",)),
    ExecutiveCapability("read_blocked", "engineering", "auto", "Supabase charlie_missions + block adjudicator", ("blocked", "stuck", "failed", "recover"), "Explain blocked work and distinguish recovery from owner discretion."),
    ExecutiveCapability("read_queue", "engineering", "auto", "Supabase charlie_missions", ("queue", "missions", "next", "approved", "backlog"), "Read the authoritative mission queue."),
    ExecutiveCapability("read_mission", "engineering", "auto", "Supabase charlie_missions", ("mission", "stage", "attempt", "matrix"), "Inspect one mission and its evidence.", required_args=("mission_id",)),
    ExecutiveCapability("read_decisions", "governance", "auto", "Owner approval inbox", ("decision", "approval", "review", "need me"), "Read genuine owner decisions."),
    ExecutiveCapability("read_analyst", "improvement", "auto", "ANALYST scorecard", ("analyst", "proposal", "learning", "improvement"), "Read improvement proposals and validation."),
    ExecutiveCapability("read_workforce", "workforce", "auto", "Workforce scorecards", ("workforce", "agent", "training", "performance"), "Read agent and workforce state."),
    ExecutiveCapability("read_business_status", "business", "auto", "Operational business services", ("business", "money", "profit", "performance"), "Read cross-business operating status.", ("read_orders_status", "read_farm_status")),
    ExecutiveCapability("read_sam_status", "sales", "auto", "SAM learning scorecard", ("sam", "livestock", "sales", "customer", "conversation"), "Read SAM readiness and learning state."),
    ExecutiveCapability("read_sam_conversation", "sales", "auto", "Chatwoot + intake state", ("conversation", "chat", "customer", "reply"), "Inspect a specific SAM conversation.", required_args=("conversation_id",)),
    ExecutiveCapability("read_beacon_status", "marketing", "auto", "Beacon workforce scorecard", ("beacon", "marketing", "campaign", "post", "media"), "Read Beacon campaign readiness."),
    ExecutiveCapability("read_orders_status", "orders", "auto", "Order service", ("orders", "sales", "quote", "collection"), "Read order portfolio status."),
    ExecutiveCapability("read_order", "orders", "auto", "Order service", ("order", "quote", "customer", "paperwork"), "Inspect an authoritative order.", required_args=("order_id",)),
    ExecutiveCapability("read_farm_status", "farm", "auto", "Pig and availability services", ("farm", "pig", "pigs", "stock", "weight", "pen", "litter"), "Read farm and livestock availability state."),
    ExecutiveCapability("read_pig", "farm", "auto", "Pig profile and weight services", ("pig", "tag", "weight", "pen", "mother", "father", "treatment"), "Inspect one pig's authoritative profile.", required_args=("pig_id",)),
    ExecutiveCapability("read_trust", "governance", "auto", "CHARLIE capability trust ledger", ("trust", "autonomy", "confidence"), "Read measured delegation trust."),
)

BY_INTENT = {item.intent_type: item for item in CAPABILITIES}


DEFAULT_PLANS = {
    "read_core_status": ("read_core_status", "read_blocked"),
    "executive_brief": ("read_core_status", "read_blocked", "read_decisions", "read_analyst"),
}


def capability_catalog():
    return [asdict(item) for item in CAPABILITIES]


def capability_metadata(intent_type):
    item = BY_INTENT.get(str(intent_type or ""))
    return asdict(item) if item else {}


def select_capabilities(owner_text, intent_type, args=None, *, limit=5):
    """Select authoritative reads by explicit intent plus owner-language relevance."""
    text = str(owner_text or "").lower()
    selected = list(DEFAULT_PLANS.get(intent_type) or ())
    if intent_type in BY_INTENT and intent_type not in selected:
        selected.append(intent_type)
    scored = []
    for capability in CAPABILITIES:
        score = sum(1 for keyword in capability.keywords if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text))
        if score and capability.intent_type not in selected:
            scored.append((score, capability.intent_type))
    selected.extend(item for _score, item in sorted(scored, key=lambda row: (-row[0], row[1])))
    return selected[:limit]


def follow_up_capabilities(evidence, already_selected, *, limit=3):
    """Choose one bounded evidence-gap pass; never repeat a capability."""
    existing = set(already_selected or ())
    candidates = []
    for item in evidence:
        capability = BY_INTENT.get(str(item.get("intent_type") or ""))
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if item.get("success") is False:
            # A failed authoritative source is reported honestly, not replaced by guessing.
            continue
        explicit = result.get("suggested_followups") or []
        for name in (*((capability.follow_ups) if capability else ()), *explicit):
            if name in BY_INTENT and name not in existing and name not in candidates:
                candidates.append(name)
    return candidates[:limit]
