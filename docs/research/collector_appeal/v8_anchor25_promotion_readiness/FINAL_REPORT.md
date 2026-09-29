# Collector V8 ANCHOR25 Promotion Readiness Review

**Date:** 2026-09-29  
**Decision:** `COLLECTOR_V8_ANCHOR25_PROMOTION_READINESS_CODE_READY_NO_PROMOTION`

Collector V8 ANCHOR25 is ready at the **code/review layer**, but no production
promotion was performed. Production remains on the exact V7 control used by the
calibration, historical replay, temporal validation, and accepted V8 shadow.

## Research authority

The preregistered ANCHOR25 candidate changes only the Trainer subject baseline:

```text
trainer_subject_v8 = 0.75 * trainer_subject_v7 + 0.25 * pokemon_anchor
```

The downstream card effect is the exact realized V7 combined headroom fraction,
not a fresh sequential Playability/Artist recomputation:

```text
fraction = (v7_card_score - v7_subject) / (100 - v7_subject)
v8_card_score = v8_subject + (100 - v8_subject) * fraction
```

Pokémon is unchanged.

Temporal validation used the five fixed dates 2026-09-14, 09-17, 09-20,
09-23, and 09-26. All 5/5 folds passed the preregistered gate with full
4,331/4,331 modeled-card coverage and positive deltas on every gated metric.
The accepted shadow decision was
`COLLECTOR_V8_ANCHOR25_SHADOW_SUPPORTED_FOR_PROMOTION_REVIEW`.

## Exact executable parity

The earlier V8 builder attempt was not equivalent to the validated candidate:
it recalculated Playability and Artist sequentially after changing the Trainer
baseline. That caused small but real card/Set differences.

The corrected builder now preserves the exact realized V7 combined headroom
fraction. Research parity workflow `36640412954` proved:

- max card parity error: **0.0**
- max Set parity error: **0.0**
- Trainer within-domain Spearman: **0.9999999999999998**
- database writes: **NONE**

Accepted V8 fingerprints:

- formula: `212bd6e679bfdb80e93ec8e8d831f242a950c628a375b89655942d6f6e970957`
- card: `0b66d491565717a9595c5c1da86f75d1c3009a13c0a7886f9dce2e8e26ebd9d7`
- Set: `71fc319f473a65743e1855260ecc7dbe87ecd21868be1c105d5100d36098daa9`

The cutover-prep workflow `36641788739` then passed **50 tests** and rebuilt
those same three fingerprints exactly.

## Live production preflight

Production Collector authority remains:

- model: `pokemon_collector_appeal_v7_expanded_price_blind_v1`
- run: `e282f26e-2136-4105-b0a3-f0974c4d9d70`
- status: published / validation passed
- model input fingerprint:
  `3b781f4ec01ef8c74c77b34d2b91e9a90231d2feccf2ee41411de64606378c9d`
- formula fingerprint:
  `06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b`
- card fingerprint:
  `7dbe5e989c6eb7bcb9d4684707f9c239ab1ca701fc429a7a0605657d79f2ab90`
- Set fingerprint:
  `744f088e7e1e33e5f8b40aca707b8f7e0d93bf7def8308b860da0277257a4b52`

There are **no V8 model runs in production**.

The active Set-page generation
`7b1b688e-4453-4c6e-b315-5e7919523408` is published and validation-passed,
with 212 Set pages and 128 Collector contracts. The live membership audit is
exact:

- V7 Set rows: **128**
- Set-page Collector contracts: **128**
- model rows missing from pages: **0**
- page contracts missing from model: **0**
- fresh rebuilt Set pages: **22**
- scored Collector Sets: **22**
- fresh/scored mismatches: **0**

## Production gaps closed in the prep branch

1. **Formula parity** — corrected the executable V8 builder to the exact
   preregistered candidate.
2. **Public contract** — V8 is recognized as the expanded
   Pokémon/Trainer/Playability/Artist model rather than falling through to an
   older methodology label.
3. **Daily continuity** — the historical operationalizer now follows whichever
   Collector formula is currently promoted (V7 or V8) and never auto-switches
   versions.
4. **Temporal history** — V7 retains its hardened DB RPC; V8 gets an idempotent,
   one-statement append path with exact model fingerprint and source lineage.
5. **Set-page authority** — a model-run cutover now overlays the target
   Collector contract across all 128 Collector-member pages, including
   carry-forward pages, while preserving unrelated snapshot fields and
   historical timestamps. It refuses to drop existing Collector membership.
6. **Component diagnostics** — V8 does not invent a new Playability/Artist
   decomposition. Those two Set-level impact diagnostics are suppressed under
   V8; Pokémon/Trainer diagnostics remain valid.
7. **Atomic cutover** — Collector pointer and Set-page generation use the
   existing transactionally coordinated promotion RPC.
8. **Interruption recovery** — reruns can reuse a validated staged generation,
   and if atomic promotion succeeded before history append failed, the command
   recognizes only the exact accepted V8 authority and completes history/readback
   without a second promotion.
9. **Overall RIP insulation** — the cutover code contains no Overall RIP
   publication path. Overall mutation remains **NONE**.

## Source-evidence freshness

No newer valid Collector source authority exists than the source runs already
bound to the V7 control. The current 7-day refresh contract nevertheless marks
three sources due by age:

- Pokémon Trends 1-month: due
- Trainer Trends 12-month: due
- Artist Trends 12-month: due

Trainer 5-year and Artist 5-year remain inside their 31-day freshness window.

This does **not** change the validated cutover identity; it means the normal
Collector operationalizer should refresh those due dynamic sources after the
cutover stack is deployed/activated and then rebuild the currently promoted
formula from the new append-only evidence.

## Safety boundary and next step

No database write, V8 stage, pointer change, Set-page activation, or Overall RIP
publication occurred during this review.

The next safe sequence is:

1. review/merge and deploy the cutover-prep code;
2. run the V8 cutover command in its default read-only mode against production;
3. require the exact V7 control/fingerprints/source lineage to still match;
4. only after separate explicit authorization, run the acknowledged commit mode;
5. read back the V8 pointer + Set-page generation and confirm V8 temporal
   history; then allow the normal due-source refresh path to proceed.

Until step 4 is explicitly authorized, **V7 remains production authority**.
