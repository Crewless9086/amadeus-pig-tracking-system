# Amadeus Farm

The farm operating system covers pigs, litters, breeding, weights, medical events, purpose review, sales, slaughter/abattoir fallback, weather, power, irrigation, and operational dashboards.

Core rule: one pig should have one operational truth.

## Command Structure

- CEO / farm commander: Oom Sakkie.
- Farm Operations: Herdmaster, Rootline, Gatekeeper, Quartermaster.
- Farm Sales CEO: SAM.
- Farm Sales lanes: meat sales, live pig sales, slaughter/abattoir sales, butcher/custom-cut sales.

Oom Sakkie owns farm command and operational truth. SAM owns farm sales/client interaction. Farm Sales agents must draw from the same farm truth and must not create separate shadow truth.

Source references: `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`, `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`.
