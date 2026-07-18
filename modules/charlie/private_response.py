"""Owner-safe structured responses for CHARLIE Live Executive."""

from __future__ import annotations

import re


def build_executive_response_packet(reply, *, plan=None, evidence=None, context=None, action_status_code=200):
    plan = plan if isinstance(plan, dict) else {}
    evidence = evidence if isinstance(evidence, list) else []
    context = context if isinstance(context, dict) else {}
    text = _clean(reply, 3900)
    successful = [item for item in evidence if item.get("success")]
    facts = []
    evidence_rows = []
    actions = []
    for item in evidence:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        summary = _clean(result.get("summary"), 600)
        if item.get("success") and summary:
            facts.append(summary)
        if result.get("prepared_only") or result.get("mission_id"):
            actions.append(summary or _clean(item.get("tool"), 120))
        evidence_rows.append({
            "capability": _clean(item.get("intent_type") or item.get("tool"), 120),
            "domain": _clean(item.get("domain"), 80),
            "source": _clean(item.get("source_of_truth"), 180),
            "observed_at": item.get("observed_at"),
            "success": bool(item.get("success")),
            "summary": summary,
            "agent": result.get("agent") if isinstance(result.get("agent"), dict) else None,
            "direct_answer": _clean(result.get("direct_answer"), 800),
        })
    commitments = list(context.get("commitments") or [])[-10:]
    recommendation = _recommendation(text)
    return {
        "version": "charlie_live_executive_response_v1",
        "spoken_summary": spoken_summary(text),
        "display_answer": text,
        "verified_facts": facts[:6],
        "recommendation": recommendation,
        "actions_taken": [value for value in actions if value][:5],
        "commitments": commitments,
        "owner_decision": None,
        "evidence": evidence_rows,
        "active_subject": context.get("active_subject") or plan.get("subject") or {},
        "confidence": _evidence_confidence(evidence, successful, action_status_code),
        "status_code": int(action_status_code or 200),
    }


def spoken_summary(text, max_chars=520):
    clean = _spoken_text(text, 3900)
    if len(clean) <= max_chars:
        return clean
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    selected = []
    length = 0
    for sentence in sentences:
        if selected and length + len(sentence) + 1 > max_chars:
            break
        selected.append(sentence)
        length += len(sentence) + 1
    return " ".join(selected).strip() or clean[:max_chars].rsplit(" ", 1)[0] + "."


def _spoken_text(value, limit):
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+]\s|\d+[.)]\s|>\s?)", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]+", "", text)
    return " ".join(text.split())[:limit]


def _recommendation(text):
    for line in str(text or "").splitlines():
        if line.lower().strip().startswith(("recommendation:", "recommended next action:", "next:")):
            return line.split(":", 1)[-1].strip()[:500]
    return ""


def _clean(value, limit):
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _evidence_confidence(evidence, successful, status_code):
    if not evidence:
        return 1.0 if status_code < 400 else 0.0
    scores = []
    for item in successful:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        try:
            scores.append(max(0.0, min(1.0, float(result.get("confidence")))))
        except (TypeError, ValueError):
            scores.append(1.0)
    if not scores:
        return 0.0
    completion = len(successful) / len(evidence)
    return round((sum(scores) / len(scores)) * completion, 2)
