# Vintage partial-known snapshot repair — 2026-09-29

## Decision

Edition-scoped Set Value snapshots may publish when exact edition identity is complete but one or more card prices are unresolved.

The published current value is **the subtotal of known exact-edition card prices**. Unknown cards remain in the constituent roster with `marketPrice = null` and `priceStatus = unknown`. Generic Holofoil or another edition is never substituted.

Historical price performance remains fail-closed unless the current scope is complete and the existing scoped-history certification is publishable.

## 2026-09-28 repaired scopes

| Market | Known subtotal | Priced / expected | Coverage | Unknown |
| --- | ---: | ---: | ---: | ---: |
| Base — 1st Edition | $8,409.84 | 93 / 102 | 91.18% | 9 |
| Base — Shadowless | $6,599.53 | 101 / 102 | 99.02% | 1 |
| Neo Destiny — 1st Edition | $17,036.98 | 112 / 113 | 99.12% | 1 |
| Neo Revelation — 1st Edition | $4,805.09 | 65 / 66 | 98.48% | 1 |
| Neo Revelation — Unlimited | $2,683.00 | 65 / 66 | 98.48% | 1 |

All five known subtotals reconcile exactly to their priced exact-edition constituent rows. The full expected identity roster also reconciles exactly: 13 unresolved prices across the five markets.

## Publication semantics

Partial scopes publish with:

- `availability = available`
- `currentValueStatus = partial_known_only`
- `currentValueDefinition = sum_known_exact_edition_card_prices`
- `currentScopedValueCertified = false`
- `unknownPricesExcludedFromTrackedValue = true`
- `genericOrCrossEditionFallbackUsed = false`
- expected/priced/unknown counts and coverage in directory metadata
- `history_available = false` until complete comparable history is certified

Complete scoped markets retain the existing certified behavior.

## Raw reconciliation discovered during promotion

The first full rebuild was blocked by a $59.14 Raw reconciliation mismatch. It was isolated to POP Series 1 on 2026-09-28:

- root shadow authority: $720.07 / 17 cards
- stale frozen constituent publication: $779.21 / 17 cards
- difference: $59.14

A bounded repair rebuilt that one 17-card publication with the same selector used by the current standard-root shadow authority. The repaired frozen roster is $720.07 with fingerprint `ac12e3befd6c2652216e528007eb1ae1`.

The repair deliberately did **not** change the publication precedence for earlier dates. An audit found 238 standard shadow-vs-publication mismatches across five dates (2026-09-24 through 2026-09-28), with much larger differences on September 24–27 from legacy recovery rosters. Treating all frozen publications as universal historical authority would therefore have rewritten prior Raw history and was rejected.

## Serving generation

A same-date repair generation was created by cloning the prior validated 2026-09-28 surface, then rebuilding only the edition-scoped overlays and Raw surface, followed by metric finalization and full validation.

- serving generation: `a057ef42-512d-4757-bf20-85ee96b544d6`
- previous generation: `a4f714b6-83bf-465d-984b-6e12d6d1c797`
- validation: `VALIDATED`, zero issues
- coherence assertion: `COHERENT`
- directory rows: 392
- history rows: 60,239
- constituent rows: 130,362
- Raw leaf count: 20,313
- Raw basket value: $452,085.91
- unresolved scoped constituent rows: 13

