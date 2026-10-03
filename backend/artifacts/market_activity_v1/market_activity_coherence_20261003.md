# Market Activity coherence correction — 2026-10-03

## Candidate generation — STOPPED BEFORE PROMOTION

`e6b6c276-edba-48f5-9326-7c462796d0aa`

- Market: `set:7a3dd188-4375-41af-94de-c5247fe0b1a6` (Prismatic Evolutions Card Market)
- As of: `2026-10-02`
- Explorer surface: `5caf929a-4962-4334-84a0-c75d3635135b`
- State: `VALIDATED`
- Serving state: `RETAINED`
- Promoted: `false`
- Provider calls: `0`

## Plan receipt

- Elapsed: 59.522063 seconds
- Source queries: 175
- Evidence rows read: 6,119
- Batches: 4
- Roster fingerprint: `53cb1dc85a1de229426c1bb27dba121d16ff220ccdf2ca635e71b0806684def2`
- Errors: none

## Stage and persisted validation receipt

- Elapsed: 61.44079 seconds
- Rows written: 2,306
- Roster: 174/174
- Instrument payloads: 174/174
- Series metadata: 174/174
- Instrument windows: 696
- Group windows: 7, 30, 90, 180
- Daily Activity history rows: 868
- Generation/surface coherence: valid
- Capability eligible after an independent successful promotion: true
- Validation errors: none

Production capability discovery remains intentionally unavailable because the
older generation is still serving. The current read-only coherence receipt is
0 coherent of 1 supported market and reports `unavailable_pending_refresh`.
The generation mismatch safety check was not weakened.

## Recurrence correction

The scheduled maintained-cache prewarm path already owns the current Explorer
V2 publication handoff. After that V2 publisher returns `promoted`,
`promoted_existing_validated`, or `already_current`, it now invokes a bounded,
provider-free Activity convergence worker.

The worker:

- finds only markets already present in Activity serving authority;
- is idempotent when every market is coherent;
- builds against the exact current Explorer generation and market date;
- promotes only a `VALIDATED` candidate after re-reading the Explorer pointer;
- leaves the old pointer untouched on validation failure or a surface race;
- caps one invocation at 10 supported markets and 600 seconds;
- reports zero provider calls.

The market freshness watchdog now reports
`market_activity_generation_mismatch / activity_surface_generation_mismatch`
whenever any serving Activity market trails the Explorer surface.

## UI acceptance

The deterministic coherent fixture proves that focusing Prismatic exposes an
available Market Activity control, entering Activity renders the chart, and
returning to Performance preserves all active market keys and Prismatic focus.
Screenshot: `fma3/1440x900-prismatic-activity-exit-retains-workspace.png`.

The live production UI remains unavailable until an operator independently
audits and promotes the candidate above.
