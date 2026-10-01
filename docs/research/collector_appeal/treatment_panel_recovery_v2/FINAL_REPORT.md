# Treatment Panel Recovery V2 — Final Report

Decision: `TREATMENT_PANEL_RECOVERY_V2_PASS_PHASE2_REOPENED`

## Frozen pilot

- 16 matched subject/mechanic identities
- 36 canonical cards
- 7 Sets
- 4 treatment families
- all Sets are inside the September 29, 2026 simulation-supported cohort

Families:

- Common ↔ Illustration Rare: Shrouded Fable, White Flare
- Illustration Rare ↔ Uncommon: Black Bolt, Paldea Evolved
- Double Rare ↔ Ultra Rare: Paradox Rift, Surging Sparks
- Double Rare ↔ Special Illustration Rare ↔ Ultra Rare: Scarlet and Violet 151, Surging Sparks

## Collection result

Workflow run: `36913676646`
Artifact: `11190000187`
Artifact digest: `sha256:e1cafb46732bf40932c8095b8f8266b05d256d2fdaa5761afc0fe1078be86233`

- provider requests: 92
- PkmnPrices credits used: 3,521
- configured hard cap: 7,500
- cards collected: 36 / 36
- blocked cards: 0
- historical rows: 3,465
- exact condition: Near Mint
- exact provider printing variant verified for every card
- database writes: 0
- canonical-price mutation: none
- Collector / Overall RIP mutation: none

Every selected card also has authoritative exact-variant modeled pull probability in the September 29 simulation cohort.

## Readiness result

All 16 identities passed the frozen Round-24 controlled threshold:

- PANEL_READY_MODERATE: 16
- HISTORY_BLOCKED: 0
- METADATA_BLOCKED: 0

Shared-date counts range from 91 to 98.

All eight Set/family groups have two ready identities. Four Scarlet & Violet era-family comparisons therefore clear the already-frozen two-independent-Set progression gate.

## Source bridge

Treatment Hierarchy V1 had frozen Price Storage V2 and explicitly prohibited substituting a new pricing authority. Therefore the recovered PkmnPrices panel is NOT silently treated as V1 authority.

Before any Treatment estimator is fit, a source-bridge check compared PkmnPrices TCGPlayer Near-Mint history with canonical TCGPlayer NM observations on a representative one-card-per-Set sample across the seven pilot Sets (48 exact overlapping card-dates):

- median absolute relative difference: 0.3508%
- P90 absolute relative difference: 2.8779%
- P95 absolute relative difference: 4.6014%
- maximum absolute relative difference: 8.3333%
- share within 5%: 93.75%
- share within 10%: 100%
- median signed relative difference: 0.0%
- mean signed relative difference: -0.0904%
- log-price Pearson correlation: 0.9999583

This is strong descriptive evidence that the recovered endpoint is measuring the same TCGPlayer NM market-price construct, but it does not retroactively alter V1's preregistration. A separate V2 estimator contract is frozen before fitting.

## Disposition

The historical-panel blocker that stopped Treatment Hierarchy V1 is removed for this modern pilot.

The next authorized research step is Treatment Hierarchy V2 Set-local / Scarlet & Violet era-level estimation under the separately frozen V2 estimator contract. Cross-era conclusions remain unauthorized until a second era independently clears the required evidence gates.
