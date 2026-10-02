# Treatment Graph V1 — Structural Preregistration

Status: `PREREGISTERED_BEFORE_ADDITIONAL_FAMILY_OUTCOMES`

## Purpose

Extend the validated Set-relative Treatment research into a connected modern
Treatment graph without assigning universal rarity scores a priori.

Edge selection below is based only on matched-identity support in the frozen
2026-09-29 22-Set simulation cohort. It is not selected by observed treatment
effect direction or magnitude.

## Frozen graph principle

Each edge is estimated locally from same-subject, same-Set, exact-date Near-Mint
price panels with:

- exact modeled pull probability as scarcity control;
- frozen Collector V7 Subject Appeal;
- frozen Playability;
- frozen Artist control;
- whole-subject bootstrap;
- early/late temporal split;
- no interpolation or forward fill.

A Set-family estimate requires >=2 independent matched identities. An era-family
edge requires >=2 passing Sets. Unsupported edges remain unavailable.

## Primary connected edges

These edges form the minimum connected modern graph:

1. `Common ↔ Illustration Rare`
2. `Illustration Rare ↔ Rare`
3. `Illustration Rare ↔ Uncommon`
4. `Uncommon ↔ Ultra Rare`
5. `Ultra Rare ↔ Double Rare`
6. `Ultra Rare ↔ Special Illustration Rare`
7. `Double Rare ↔ Mega Hyper Rare` — Mega Evolution era only
8. `Ultra Rare ↔ Hyper Rare` — Scarlet & Violet era only

## Redundancy / loop-validation edges

These are estimated where supported to test graph consistency rather than define
connectivity:

9. `Double Rare ↔ Special Illustration Rare`
10. `Hyper Rare ↔ Special Illustration Rare` — Scarlet & Violet
11. `Double Rare ↔ Hyper Rare` — Scarlet & Violet

## Frozen structural support observed before additional pulls

### Mega Evolution era

- Common ↔ Illustration Rare: 6 G1-ready Sets / 44 ready identities
- Double Rare ↔ Ultra Rare: 6 / 44
- Double Rare ↔ SIR: 6 / 37
- Illustration Rare ↔ Uncommon: 6 / 37
- Ultra Rare ↔ Uncommon: 6 / 19
- SIR ↔ Ultra Rare: 5 / 33
- Illustration Rare ↔ Rare: 5 / 18
- Double Rare ↔ Mega Hyper Rare: 2 / 4

### Scarlet & Violet era

- Double Rare ↔ SIR: 16 / 99
- SIR ↔ Ultra Rare: 15 / 124
- Common ↔ Illustration Rare: 14 / 202
- Double Rare ↔ Ultra Rare: 14 / 150
- Illustration Rare ↔ Rare: 13 / 63
- Ultra Rare ↔ Uncommon: 13 / 62
- Illustration Rare ↔ Uncommon: 12 / 117
- Double Rare ↔ Hyper Rare: 9 / 29
- Hyper Rare ↔ SIR: 9 / 28
- Hyper Rare ↔ Ultra Rare: 8 / 26

## Graph fitting rule

After each edge passes its own evidence gates, solve treatment-node positions on
the log-effect scale by weighted least squares using inverse uncertainty as
weights. Set-specific estimates remain first-class outputs; era pooling and the
global graph are secondary summaries.

Do not force a monotonic order.

Loop closure is a validation diagnostic. For example, the independently
estimated path:

`Double Rare → Ultra Rare → SIR`

must be consistent, within uncertainty, with the direct:

`Double Rare → SIR`

edge. Similar loop checks apply to Hyper Rare.

## Normalization

Do not define a 0–100 Treatment Appeal score until:

- the connected graph has at least one validated path for every node included in
  the score;
- primary and redundancy loops are acceptably coherent;
- early/late signs and rank structure are stable;
- unsupported treatment families remain explicitly unavailable.

Candidate normalization methods remain the previously preregistered robust
cross-era methods; no normalization is selected in this document.

## Current validated / in-progress anchors

- SIR ↔ Ultra Rare: pilot supported
- Double Rare / Ultra Rare / SIR three-level pilot: estimated
- Hyper Rare / Ultra Rare / SIR: pilot estimated; full-set expansion pending
- exhaustive Double Rare / Ultra Rare / SIR expansion: pending

## Safety

Research only. No production price authority, Collector Appeal, Overall RIP,
Rankings, or Set-page writes are authorized by this preregistration.
