# UI Dashboard Standard

Owner dashboards must help Charl decide quickly. They must not bury decisions, hide buttons, overflow, or look like raw technical dumps.

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
