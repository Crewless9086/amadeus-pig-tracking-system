# Oom Sakkie Browser Behavior Checklist

Use this after local UI/runtime foundation changes that touch the System Workbench, agent dry-run rails, voice controls, or review panels.

## Scope

- Local browser check only.
- No specialist dispatch.
- No specialist LLM execution.
- No specialist tool execution.
- No farm-data writes.
- No public/customer output.
- No Builder/Forge execution, patch application, deploy, Telegram cutover, or physical control.

## Setup

1. Start the local app.
2. Open `/oom-sakkie` in Chrome.
3. Open DevTools console.
4. Keep the Network tab visible if you are checking fetch behavior.

## Multi-Specialist Dry-Run UI

1. Open `System Workbench`.
2. Refresh `Agent Roadmap`.
3. Confirm `Approved dry-run candidates` lists Sentinel, Prism, Atlas, Ledger, Rootline, Herdmaster, Butcher, and Quartermaster.
4. Confirm Beacon, Forge, and Gatekeeper do not appear as approved dry-run request candidates.
5. Select Ledger in the approved-specialist dropdown and click `Request Selected Dry-Run`.
6. Confirm a Ledger dry-run request appears in `Agent Dry-Run Requests`.
7. Confirm the guard text says dispatch, specialist LLM, specialist tools, and writes are off.
8. Confirm no request is created until the button is clicked.

## Handoff And Result Review

1. Click the handoff/open action on a dry-run request.
2. Confirm the handoff names the selected specialist.
3. Confirm the handoff says not to call tools, not to produce code, and not to approve itself.
4. Record a small test result for that request.
5. Confirm the result appears in `Agent Result Review`.
6. Open the review packet.
7. Confirm `Evidence kind`, `May influence`, `Must not influence`, and `Owner question` are visible.
8. Confirm accepting/rejecting/adding a review note requires an explicit button click.

## Learning And Roadmap

1. Accept one dry-run result for learning.
2. Refresh `Agent Learning Ledger`.
3. Confirm only accepted evidence appears.
4. Refresh `Agent Roadmap`.
5. Confirm `Accepted agent learning` shows `accepted by specialist ...`.
6. Confirm runtime, dispatch, specialist LLM/tool, and write guards remain locked.

## No Background Polling

1. Leave the Workbench open for two minutes without clicking.
2. Confirm no repeated background polling appears in the Network tab.
3. Confirm review/event POST requests happen only after explicit owner clicks.

## Voice Controls

1. Click the talk button.
2. Confirm the browser microphone starts only after the click.
3. Ask one question.
4. Confirm the microphone stops after the utterance.
5. Enable `Continue conversation`.
6. Confirm the loop counter appears and cannot exceed `Voice loop 5 of 5`.
7. Say `stop conversation`, `cancel`, or `never mind`.
8. Confirm the loop stops and the microphone is not left open.

## Pass Criteria

- No console errors.
- No timer-style background polling.
- No hidden POST requests.
- Every dry-run/result/event action is owner-clicked.
- All runtime/dispatch/write/public-output/control guards remain locked.
