# Agent Asset Register

## Purpose

This register tracks the approved image and voice assets for Oom Sakkie and the specialist agents.

The product vision lives in `docs/00-start-here/PRODUCT_VISION.md`. Runtime asset metadata lives in `static/assets/agents/agent_registry.json` and each agent folder's `agent.json`.

## Canonical Asset Folder

Use this repo folder for web-served assets:

```text
static/assets/agents/
```

Browser paths use:

```text
/assets/agents/
```

The Flask app serves this browser path from `static/assets/` through the `/assets/<path>` route. Keep this route tested; otherwise the UI falls back to initials even when the files exist.

Do not use `/public/assets/agents/` in this Flask app unless a new public static rule is deliberately added later.

## Naming Rules

Use lowercase file names.

Use this pattern:

```text
agentid_assettype_context_state_version.extension
```

Examples:

```text
oom-sakkie_portrait_main_neutral_v01.png
ledger_portrait_panel_neutral_v01.png
herdmaster_portrait_dock_neutral_v01.png
sam_voice_preview_en_v01.mp3
gatekeeper_voice_preview_blocked_v01.mp3
oom-sakkie_animation_speaking_v01.webm
```

Do not overwrite old approved versions. Add a new version number and update the relevant `agent.json` and `agent_registry.json` path.

## Current Asset Status

| Agent ID | Display Name | Image Status | Voice Status | Notes |
| --- | --- | --- | --- | --- |
| `oom-sakkie` | Oom Sakkie | Static portrait added as valid PNG files: `oom-sakkie_portrait_main_neutral_v01.png` and dock portrait | Voice candidate: Mikey Slater - Motivational Speaker (`3y3q5VpFXdeyf5ooB12e`), not production-approved yet | Start with static portrait and CSS state motion. |
| `ledger` | Ledger | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |
| `herdmaster` | Herdmaster | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |
| `beacon` | Beacon | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |
| `sam` | Sam | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |
| `gatekeeper` | Gatekeeper | Pending generation/upload | Pending ElevenLabs selection | Always visible; quiet unless blocked/approval signals exist. |
| `rootline` | Rootline | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |
| `butcher` | Butcher | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |
| `quartermaster` | Quartermaster | Pending generation/upload | Pending ElevenLabs selection | Same semi-realistic farm command style. |

## Placement Checklist

For each agent:

1. Save panel portrait in `static/assets/agents/<agent-id>/portraits/`.
2. Save dock portrait in `static/assets/agents/<agent-id>/portraits/`.
3. Save voice preview files in `static/assets/agents/<agent-id>/voice/`.
4. Update `static/assets/agents/<agent-id>/agent.json`.
5. Update `static/assets/agents/agent_registry.json`.
6. Mark approved production choices in this register.

## Current Answers

- Create folders and starter metadata now: yes.
- Oom Sakkie starts with a static portrait first: yes.
- Motion starts with CSS state rings/glow/waveform: yes.
- WebM/mouth animation can come later: yes.
- All agents use the same semi-realistic visual family as Oom Sakkie: yes.
- Gatekeeper remains visible in the dock: yes.
- Gatekeeper should be visually quiet when nothing is blocked, and visually stronger when approvals or blocked actions exist: yes.
