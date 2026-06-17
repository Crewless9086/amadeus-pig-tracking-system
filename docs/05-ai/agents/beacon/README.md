# Beacon Agent

## Purpose

Beacon is the farm's market voice and demand-generation agent.

Beacon should turn real farm readiness into controlled public demand:

- what is becoming ready to sell,
- which sale stream should be promoted,
- what story/offer should be used,
- which channel should carry it,
- which approved media asset should support it,
- when it should run,
- how much spend is allowed,
- whether the campaign is working,
- and what should be changed, paused, boosted, or repeated.

## Current Implementation

Phase 11N is the first safe slice:

- `modules/sales/beacon_campaign.py` builds a draft-only meat launch campaign packet.
- `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` stores the first pork freezer preorder copy packet for owner review.
- `tests/test_beacon_campaign.py` proves the packet has no posting, sending, quoting, ordering, stock, reservation, booking, or payment authority.

This is not yet full Beacon automation. It is the first campaign-draft foundation.

## Canonical Scope

The long-term Beacon scope is captured in:

- `docs/05-ai/agents/beacon/BEACON_SCOPE.md`

That file is the source of truth for future Beacon builds.
