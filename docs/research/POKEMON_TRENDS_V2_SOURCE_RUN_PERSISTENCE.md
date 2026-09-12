# Pokémon Trends V2 source-run persistence bridge

Status: implementation ready; production migration and ingestion not executed.

The completed 1,025-row checkpoint now has a narrow bridge into the existing
`pokemon_collector_source_runs` and `pokemon_collector_entity_observations` lifecycle.
Live read-only inspection confirmed 1,025 active Pokémon collector entities keyed to
the canonical `pokemon_reference` identities. The generic observation table already
supports Pokémon as first-class entities, append-only evidence, run-scoped uniqueness,
and full JSON provenance, so no parallel or Pokémon-specific table was added.

## Persistence contract

The source run records source/capture identity, the full checkpoint SHA-256,
manifest fingerprint/version, capture and ingestion code versions, timeframe, geo,
capture start, terminal counts, and diagnostics. Each observation records the exact
source run and canonical entity plus calibrated Trends value, final anchor, ladder
rung, raw target/anchor, retry/escalation summary, classification, failure detail,
manifest/capture/calibration versions, query settings, and row capture timestamp.

`SCORED` and `scored_zero_high_confidence` are numeric. `failed`,
`missing_evidence`, and `insufficient_calibration` are unavailable and must remain
null. The exact unbounded calibrated value remains in provenance; the generic
0–100 observation field contains its bounded representation required by the existing
schema. Downstream reads return the exact provenance value and require an explicit
terminal `source_run_id`; there is no implicit “latest” fallback.

## Idempotency and atomicity

Capture identity hashes the frozen header and all canonical JSON checkpoint rows.
A Pokémon-V2-only partial unique index and transaction advisory lock serialize the
same capture. The atomic RPC either returns the existing valid terminal run or inserts
the run, all 1,025 observations, and the terminal transition in one transaction.
Any validation or insert failure rolls everything back. Existing lifecycle triggers
continue to prohibit late observation inserts and mutations of terminal runs.

## Real-checkpoint dry run

- Capture SHA-256: `1beb2e02dcc636062309ccea6148674de788bcabd5d42068b5722cc4e5948c35`
- Rows / unique canonical subjects: 1,025 / 1,025
- Entity matches: 1,025; unmatched: 0
- `SCORED`: 993
- `scored_zero_high_confidence`: 27
- `failed`: 5
- `missing_evidence`: 0
- `insufficient_calibration`: 0
- Anchor distribution: Purugly 260, Stunky 260, Torkoal 254, Lucario 152,
  Charizard 56, Pikachu 43
- Manifest: `pokemon_trends_anchor_ladder_manifest_v1` / `009418a05f6b9631`
- Capture code: `capture_pokemon_trends_anchor_ladder_v2_r1`
- Planned writes when separately authorized: one source run and 1,025 observations
- Mutations performed in this task: 0

The production application order is migration first, followed by the ingestion command
with both explicit write flags. Neither action is authorized or performed here.

TRENDS_V2_SOURCE_RUN_PERSISTENCE_READY
