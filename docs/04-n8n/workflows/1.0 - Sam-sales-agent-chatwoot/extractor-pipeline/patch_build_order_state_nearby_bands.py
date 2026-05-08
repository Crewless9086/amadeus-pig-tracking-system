"""
Patch Code - Build Order State in workflow.json: stronger partial-stock band parsing
+ merge with last_agent_offer.caps (matches Code-Build-Sync-Existing-Draft-Payload.js).

Run from repo: python docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/extractor-pipeline/patch_build_order_state_nearby_bands.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WF = HERE.parent / "workflow.json"
NODE_NAME = "Code - Build Order State"

FN_MARKER = "function extractAdjacentBandOffersFromTranscript(raw) {"
OLD_BLOCK_END = "\n\nfunction hasCoreMemory"

NEW_BLOCK = r'''/**
 * Recover band/qty adjacent offers from Sam transcript + last_agent_offer caps.
 * Omits "N weaners X-Y kg" customer lines (primary intent, not addon bands).
 */
function bandLowBoundForMix(wr) {
  const m = String(wr || "").match(/^(\d+)_to_(\d+)/i);
  return m ? Number(m[1]) : 9999;
}

function mergeAdjacentBandsWithOfferCaps(parsedBands, caps, prefWr) {
  const map = new Map();
  const arr = Array.isArray(parsedBands) ? parsedBands : [];
  for (const b of arr) {
    if (!b || !b.weight_range || b.weight_range === prefWr) continue;
    const q = Number(b.quantity || 0);
    if (!(q > 0)) continue;
    const wr = b.weight_range;
    map.set(wr, Math.max(map.get(wr) || 0, q));
  }
  const capRows = Array.isArray(caps) ? caps : [];
  for (const c of capRows) {
    const wr = cleanText(c.weight_range || "");
    if (!wr || wr === prefWr) continue;
    const mq = Number(c.max_qty);
    if (!(mq > 0)) continue;
    map.set(wr, Math.max(map.get(wr) || 0, mq));
  }
  return [...map.entries()]
    .map(([weight_range, quantity]) => ({ weight_range, quantity }))
    .sort((a, b) => bandLowBoundForMix(a.weight_range) - bandLowBoundForMix(b.weight_range));
}

function extractAdjacentBandOffersFromTranscript(raw) {
  const rawText = cleanText(raw);
  if (!rawText) return [];

  const normalized = rawText
    .replace(/\u2013/g, "-")
    .replace(/\u2014/g, "-")
    .replace(/\u2212/g, "-")
    .replace(/[\u2010\u2015\uFE58\uFE63\uFF0D]/g, "-");
  const out = [];

  function pushQty(low, high, qty) {
    const lowN = Number(low);
    const highN = Number(high);
    const qtyN = Number(qty);
    if (!(lowN > 0) || !(highN > 0) || !(qtyN > 0)) return;
    const canon = normalizeWeightRange(`${lowN}-${highN}kg`);
    if (!canon) return;
    const existingIndex = out.findIndex((entry) => entry.weight_range === canon);
    if (existingIndex >= 0) {
      out[existingIndex].quantity += qtyN;
    } else {
      out.push({ weight_range: canon, quantity: qtyN });
    }
  }

  let mm;
  const reAvail =
    /(\d+)\s+available\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg(?:\s+range)?\b/gi;
  while ((mm = reAvail.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const reThereAre =
    /there\s+are\s+(\d+)\s+available\s+in\s+the\s+(\d+)\s*-\s*(\d+)\s*kg/gi;
  while ((mm = reThereAre.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx2 = /\band\s+(\d+)\s+at\s+(\d+)\s*-\s*(\d+)\s*kg/gi;
  while ((mm = rx2.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx3 = /\b(\d+)\s+pigs?\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg\b/gi;
  while ((mm = rx3.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rxBareInKg =
    /\b(\d+)\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg(?:\s+range)?\b/gi;
  while ((mm = rxBareInKg.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  return out;
}'''

OLD_CHUNK = """  const transcriptChunks = [
    cleanText(item.ConversationHistory || ""),
    cleanText(item.conversation_notes || ""),
    cleanText(item.ai_output || "")
  ].filter(Boolean);

  let adjacentBands = [];
  for (const chunk of transcriptChunks) {
    adjacentBands = extractAdjacentBandOffersFromTranscript(chunk);
    if (adjacentBands.length > 0) break;
  }

  let remainderAddonNeed = Math.max(0, requestedQtyNum - draftAllocatedCount);"""

NEW_CHUNK = """  const transcriptChunks = [
    cleanText(item.ConversationHistory || ""),
    cleanText(item.conversation_notes || ""),
    cleanText(item.ai_output || "")
  ].filter(Boolean);

  const mergedPartialStockTranscript = transcriptChunks.join("\\n");
  let adjacentBands = mergeAdjacentBandsWithOfferCaps(
    extractAdjacentBandOffersFromTranscript(mergedPartialStockTranscript),
    (item.last_agent_offer || {}).caps,
    requestedWeightRange
  );

  let remainderAddonNeed = Math.max(0, requestedQtyNum - draftAllocatedCount);"""


def main() -> None:
    wf = json.loads(WF.read_text(encoding="utf-8"))
    for n in wf.get("nodes", []):
        if n.get("name") != NODE_NAME:
            continue
        code = n.setdefault("parameters", {}).setdefault("jsCode", "")
        i_fn = code.find(FN_MARKER)
        if i_fn < 0:
            raise SystemExit(f"{NODE_NAME}: {FN_MARKER} not found")
        i0 = code.rfind("/**", 0, i_fn)
        if i0 < 0:
            raise SystemExit(f"{NODE_NAME}: doc comment before extract fn not found")
        i1 = code.find(OLD_BLOCK_END, i_fn)
        if i1 < 0:
            raise SystemExit(f"{NODE_NAME}: block end not found")
        code = code[:i0] + NEW_BLOCK + code[i1:]
        if OLD_CHUNK not in code:
            raise SystemExit(f"{NODE_NAME}: transcript chunk block not found")
        code = code.replace(OLD_CHUNK, NEW_CHUNK, 1)
        n["parameters"]["jsCode"] = code
        break
    else:
        raise SystemExit(f"Node not found: {NODE_NAME}")
    WF.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Patched {NODE_NAME} in {WF}")


if __name__ == "__main__":
    main()
