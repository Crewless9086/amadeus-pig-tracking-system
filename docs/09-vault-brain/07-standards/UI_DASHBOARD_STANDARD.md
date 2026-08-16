# UI Dashboard Standard

Owner dashboards must help Charl decide quickly. They must not bury decisions, hide buttons, overflow, or look like raw technical dumps.

All Amadeus Farm operational-page facelifts must also follow `AMADEUS_FARM_UI_FACELIFT_STANDARD.md`. The live dashboard and approved descendant pages are the visual baseline; never approximate them from an older checkout or substitute a second component system.

## Required Dashboard Principles

- Put critical owner actions directly where the decision appears.
- Do not hide approval buttons only inside fragile modals.
- Make loaded, empty, error, blocked, and unavailable states explicit.
- Show source-of-truth state and last updated time.
- Keep technical details available but secondary.
- Use compact operational panels, not decorative marketing layouts.
- Use clear labels and short action names.
- Avoid one-note palettes and unreadable contrast.
- Do not let long IDs, JSON, or filenames break layout.
- For UI missions, follow `docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md`.
- Dashboard work is not review-ready until real desktop/laptop and mobile visual evidence exists for the changed page.
- Attached reference screenshots must be cited and compared against the built screen.

## Human-first identity and owner preview gate

- Present the canonical animal or person name first, a meaningful tag second, and internal IDs last as muted technical evidence.
- Never use an internal ID as the primary owner-facing identity. When both name and tag are unavailable, show an explicit unknown identity label and retain the ID only as technical evidence.
- Resolve relationship identities through the canonical provider contract; do not make owners interpret raw relationship IDs.
- Use only validated internal destinations supplied by the owning backend when that contract provides them. Reject malformed, external, protocol-relative, backslash-normalized and unrelated destinations.
- An owner-visible UI candidate must be classified `READY_FOR_OWNER_PREVIEW` with its exact combined source revision, local URL, desktop/mobile evidence and proportional interaction coverage.
- Do not merge or deploy a preview-gated candidate until Charl approves that exact preview and exact source revision.
- Any subsequent source change invalidates the visual approval and requires a fresh exact-revision preview.

## CHARLIE Dashboard Requirements

The `/charlie` dashboard must show:

- mission counts;
- active runner state;
- next approved mission;
- review backlog;
- review decision buttons;
- command center truth;
- Vault/data/model/tool readiness;
- improvement proposals;
- runner boundary: dashboard does not run shell commands.

Owner Review cards must show:

- mission id/title/status;
- local preview/PR/test summary;
- short evidence;
- owner comments field;
- return stage;
- direct buttons: Approve Final, Send Back, Pause, Reject, Mark Done;
- Open Review for full detail.

## Oom Sakkie Dashboard Requirements

Oom Sakkie must feel like a farm command room, not a generic admin page:

- Oom Sakkie remains central;
- farm attention is visible immediately;
- decision rail shows approvals/blocked actions;
- specialist dock is visible;
- agents open as specialist panels, not random table pages;
- system workbench remains secondary.

## SAM Dashboard Requirements

SAM surfaces must show:

- lead/customer state;
- next gate;
- quote/payment/document status;
- missing facts;
- WhatsApp window/template state;
- operator action;
- no false final booking/payment/stock claims.

## Beacon Dashboard Requirements

Beacon surfaces must show:

- media approval status;
- campaign draft packet;
- public-use gates;
- exact post copy;
- selected approved media;
- spend recommendation and cap;
- manual/public post evidence;
- performance evidence.
