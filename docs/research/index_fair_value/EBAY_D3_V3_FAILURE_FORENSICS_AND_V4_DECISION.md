# eBay D3 v3 failure forensics and V4 decision

## Decision

**V4_NO_GO.** A field-only v4 is not technically justified under the stated constraints.
Only one of the five unique final HIGH false positives has an affirmative deterministic
remedy in the captured Browse data. Coverage can plausibly move above 80%, but zero
known catastrophic HIGH errors cannot.

The frozen v3 result remains `EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED`. This analysis
does not alter matcher logic, thresholds, cohorts, labels, or certification artifacts.

## False-positive accounting

The precision cohort contains three logical HIGH FPs and the coverage cohort contains
two. None is in the 16-row overlap, so there are **five logical FPs and five unique
listing FPs**.

| Row | Item | Precision | Coverage | Target / number | Frozen gold | Primary cause | Deterministic remedy |
|---|---|---:|---:|---|---|---|---|
| D3-40DD04D2C3514968 | `v1\|298609211354\|0` | no | yes | Zweilous / 147 | LOT_OR_BUNDLE | OTHER: frozen-gold audit semantic inconsistency | no |
| D3-4D319717EA4D8095 | `v1\|287082437405\|0` | yes | no | Penny / 252 | WRONG_CARD_NUMBER | SOURCE_DATA_WRONG_OR_INCONSISTENT | no |
| D3-B4A0AA245FDD3A77 | `v1\|397876491070\|0` | yes | no | Pikachu ex / 276 | SEALED_OR_ACCESSORY | RULE_MISSING | yes: `In Extended Art Frame` |
| D3-DA8965C3B1981AF2 | `v1\|800627950819\|0` | no | yes | Jamming Tower / 261 | WRONG_CARD_NUMBER | SOURCE_DATA_WRONG_OR_INCONSISTENT | no |
| D3-F7121A2D28C075DC | `v1\|318826606297\|0` | yes | no | Pikachu ex / 276 | LOT_OR_BUNDLE | OTHER: frozen-gold audit semantic inconsistency | no |

All five were classified `SINGLE_RAW_CARD` and granted HIGH by
`THREE_FACTOR_IDENTITY`. Their condition is `Ungraded`, condition ID is `4000`,
category is empty, localized aspects are empty, and subtitle is absent. Buying options
are ordinary fixed-price offers; only the framed row also has `BEST_OFFER`. The JSON
artifact records every available field and the complete v3 identity evidence.

The framed listing is a genuine missing ontology rule. A bounded `frame`/`framed`
accessory token rejects it with zero known HIGH TP loss, no recall change, and no card
loss across all 1,754 labeled rows.

The Penny and Jamming Tower titles affirmatively state the target name and collector
number; no captured structured field contradicts them. Jamming Tower's audit note says
“completely wrong card.” These are seller/source inconsistencies that deterministic
text matching cannot resolve without image interpretation.

The two frozen LOT labels deserve explicit treatment: their `audit_keep` events retain
the original LOT labels, but both audit notes say “this is the right card.” The frozen
labels remain authoritative for certification, yet those rows supply no defensible lot
token. Building phrase- or listing-specific exclusions around them would be post-hoc,
not a general matcher improvement.

## Coverage failure

The frozen metric is 55/70 (78.5714%); one additional card was required. Each uncovered
card has six observations:

| Card | Exact | MEDIUM exact | Rejected exact | Primary reason | Safe field-only recovery? |
|---|---:|---:|---:|---|---|
| Arbok | 0 | 0 | 0 | no exact target observed | no |
| Bronzor | 2 | 2 | 0 | BASE_PARALLEL_NOT_EXPLICIT | yes |
| Coalossal | 6 | 6 | 0 | BASE_PARALLEL_NOT_EXPLICIT | yes |
| Dhelmise | 1 | 1 | 0 | BASE_PARALLEL_NOT_EXPLICIT | no under a general safe rule |
| Emboar | 0 | 0 | 0 | six WRONG_CARD_NUMBER | no |
| Flareon | 4 | 0 | 4 | MULTI_CARD_OFFER (3), WRONG_VARIANT (1) | no |
| Giovanni's Charisma | 1 | 0 | 1 | WRONG_CARD_NUMBER | no |
| Grubbin | 1 | 0 | 1 | INSUFFICIENT_INDEPENDENT_EVIDENCE | no |
| Kyurem ex | 0 | 0 | 0 | five GRADED, one accessory | no |
| Leavanny | 0 | 0 | 0 | six WRONG_CARD_NUMBER | no |
| Lt. Surge's Bargain | 2 | 2 | 0 | BASE_PARALLEL_NOT_EXPLICIT | yes |
| Mega Charizard Y ex | 3 | 0 | 3 | WRONG_SET (1), WRONG_VARIANT (2) | no |
| Roaring Moon ex | 2 | 0 | 2 | NAME_CONFLICT (1), WRONG_VARIANT (1) | no |
| Team Rocket's Giovanni | 1 | 1 | 0 | BASE_PARALLEL_NOT_EXPLICIT | yes |
| Victini | 0 | 0 | 0 | five WRONG_CARD_NUMBER, one GRADED | no |

A conservative diagnostic relaxation—MEDIUM `BASE_PARALLEL_NOT_EXPLICIT`, explicit
target printed-rarity token, explicit target collector-number fraction, and no
reverse/holofoil token—promotes six exact coverage rows and no known FP. It adds
Bronzor, Coalossal, Lt. Surge's Bargain, and Team Rocket's Giovanni, producing an
evidence-supported **59/70 (84.2857%)** coverage ceiling. A broader rarity promotion is
unsafe because it promotes known wrong-variant row D2-0678.

Thus the coverage shortfall is repairable without weakening the catastrophic gate,
but the existing catastrophic FPs themselves are not field-repairable.

## Combined 1,754-row diagnostic simulation

The original 1,050 and fresh 704 item IDs are disjoint: 1,754 rows and 1,754 unique
listing IDs. These are development diagnostics only.

| Concept | TP / FP | Precision | Catastrophic FP | Recall | Card coverage | TP change | Final FPs prevented |
|---|---:|---:|---:|---:|---:|---:|---|
| frozen v3 baseline | 935 / 6 | 99.3624% | 6 | 78.1773% | 61/70 | 0 | none |
| frame-token exclusion | 935 / 5 | 99.4681% | 5 | 78.1773% | 61/70 | 0 | framed Pikachu |
| strict base-rarity promotion | 958 / 6 | 99.3776% | 6 | 80.1003% | 69/70 | +23 | none |
| both concepts | 958 / 5 | 99.4808% | 5 | 80.1003% | 69/70 | +23 | framed Pikachu |
| require structured category/aspects | 0 / 0 | undefined | 0 | 0% | 0/70 | −935 | all five, but nonviable |

The combined concepts clear raw precision and coverage but leave five catastrophic
FPs. The only field-only concept that removes every residual error destroys all known
coverage, demonstrating why missing metadata is not a workable safety gate. No result
here is independent validation.

## Wilson planning

The frozen precision result is 297/300: 99.0000%, Wilson 95% CI
97.1017%–99.6593%. Raw precision passes exactly; the required 98% Wilson lower bound
fails. For a future cohort, the minimum sample sizes whose Wilson lower bound is
strictly above 98% are:

| FPs | Minimum n | TP | Wilson lower |
|---:|---:|---:|---:|
| 0 | 189 | 189 | 98.0080% |
| 1 | 280 | 279 | 98.0051% |
| 2 | 361 | 359 | 98.0028% |
| 3 | 437 | 434 | 98.0013% |

This is planning only. It does not reinterpret v3's failed certification, and the
separate zero-catastrophic gate still applies.

## Cost and next data avenue

No v4 cycle is recommended: zero additional Browse calls and zero additional human
reviews. A smaller future certification is therefore moot. If constraints later change
to provide trustworthy structured product identifiers or image-derived identity, a new
design could be considered, but it would be a materially different evidence regime.

For Fair Value, stop treating eBay identity work as the next bottleneck. Preserve active
eBay listings only as offered-supply/asking-price diagnostics. Prioritize
transaction-grounded historical price evidence from the existing validated
TCGplayer/market-history pipeline or a licensed completed-sales source, with source-local
quality and liquidity controls before integration. No asking-price authority or Fair
Value authority is granted by this analysis.

Production mutations: **NONE**.
