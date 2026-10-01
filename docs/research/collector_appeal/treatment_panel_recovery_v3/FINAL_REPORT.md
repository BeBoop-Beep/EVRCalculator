# Treatment Panel Recovery V3 — Expanded Evidence Final Report

Decision: `TREATMENT_PANEL_RECOVERY_V3_PASS_EXPANDED_FIT_AUTHORIZED`

## Frozen expansion

- 40 matched identity-group entries
- 92 unique canonical cards
- 7 Sets
- 4 treatment families
- 5 frozen identities per Set/family
- deterministic lexicographic identity selection from the frozen Round-23 ladder authority
- all Sets inside the September 29, 2026 simulation-supported cohort

Manifest fingerprint:
`55b8dcd3090acb707d101a3b03e574862cc3ef15f752c95940870f7b4b3d6e24`

Sample fingerprint:
`7fecdbd2cb448dd9414f062d0d83b16a58b187dcbd7bf679cf781dc295d7b23e`

## Collection

Workflow run: `36929725640`

Artifact ID: `11196076068`

Artifact digest:
`sha256:e3dc70d260e53e079348db304774c89812b9a9fc0d35654ecf6d0470f1fc974b`

- provider request attempts: 279
- successful provider calls: 246
- PkmnPrices credits used: 7,950
- configured research hard cap: 18,000
- exact NM history cards recovered: 81 / 92
- historical rows recovered: 7,785
- provider condition: exact Near Mint
- exact provider printing variant verified before history use
- database writes: 0
- canonical price mutation: none
- Collector Appeal mutation: none
- Overall RIP mutation: none

## Why 11 cards stopped

All 11 blocked cards ended with the provider response:

`429 credit_limit_exceeded`

They were not blocked by canonical identity, Treatment metadata, variant ambiguity, or the research hard cap. The PkmnPrices account-level daily credit authority became the limiting resource after the successful 81-card collection.

Therefore these 11 are recorded as provider-budget truncation, not evidence that their Treatment ladders lack historical data.

No retry was attempted after the provider limit was reached.

## Panel readiness

Across the 40 frozen identities:

- `PANEL_READY_MODERATE`: 29
- `PANEL_READY_STRONG`: 0
- `HISTORY_BLOCKED`: 11

The 11 HISTORY_BLOCKED identities are downstream consequences of the provider-budget-truncated card histories above.

### Set/family readiness

| Set | Family | Frozen identities | Ready identities | Panel prerequisite |
|---|---|---:|---:|---|
| Shrouded Fable | Common ↔ Illustration Rare | 5 | 4 | PASS |
| White Flare | Common ↔ Illustration Rare | 5 | 5 | PASS |
| Scarlet & Violet 151 | Double Rare ↔ SIR ↔ Ultra Rare | 5 | 3 | PASS |
| Surging Sparks | Double Rare ↔ SIR ↔ Ultra Rare | 5 | 2 | PASS |
| Paradox Rift | Double Rare ↔ Ultra Rare | 5 | 5 | PASS |
| Surging Sparks | Double Rare ↔ Ultra Rare | 5 | 4 | PASS |
| Black Bolt | Illustration Rare ↔ Uncommon | 5 | 1 | FAIL |
| Paldea Evolved | Illustration Rare ↔ Uncommon | 5 | 5 | PASS |

Seven of eight Set/family groups retain at least two ready identities.

### Era progression

Three Scarlet & Violet treatment families retain two independent passing Sets:

1. Common ↔ Illustration Rare
2. Double Rare ↔ SIR ↔ Ultra Rare
3. Double Rare ↔ Ultra Rare

Illustration Rare ↔ Uncommon does not currently clear the era progression gate because Black Bolt has only one ready identity after provider-budget truncation.

## Research disposition

The expanded panel is sufficient to execute the already-frozen Treatment Hierarchy V3 estimator on the ready Set/family groups.

The V3 estimator contract was frozen before this collection result was inspected. It preserves the V2 estimator and all numerical support gates unchanged.

No cross-era inference is authorized.

## Safety

- production database writes: 0
- production price writes: 0
- Collector Appeal changes: 0
- Overall RIP changes: 0
- Rankings changes: 0
- Set-page changes: 0
