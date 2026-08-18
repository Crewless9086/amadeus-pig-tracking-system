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
- the normal daily workflow fits one calm, immediately useful screen without a
  long technical scroll;
- farm attention is visible immediately;
- decision rail shows approvals/blocked actions;
- specialist dock is visible;
- agents open as specialist panels, not random table pages;
- system workbench remains secondary.

The experience is warm, grounded, practical and recognizably South African
farm operations: readable in daylight, premium without corporate blandness,
and never sci-fi, robotic, militarized or gimmicky. Voice, typed commands,
Telegram and clicks are presentation adapters to the same canonical capability;
every important voice action must also be available by click or tap.

Specialist panels summarize who the specialist is, what it is watching, the
current useful state, priorities, suggestions, protected decisions, prepared
but unexecuted actions, missing evidence and its authority boundary. Technical
tables and trace evidence remain available only through deliberate deeper
workflow or audit access.

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
