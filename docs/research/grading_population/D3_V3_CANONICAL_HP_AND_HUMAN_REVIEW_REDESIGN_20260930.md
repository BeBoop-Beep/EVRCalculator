# D3 V3 canonical-HP disambiguation and reduced human review

Date: 2026-09-30

Status: research-only. No condition-normalized pricing or Fair Value authority change.

## Why V2 is not sufficient

The application already stores the Pokemon TCG API card payload on
`pokemon_canonical_cards.source_payload`, including the printed card `hp` value.
That structured field is a stronger way to distinguish a printed Pokemon HP stat
from the marketplace condition abbreviation `HP` (Heavily Played).

V2 fixed the original V1 collision by suppressing any numeric HP-looking phrase.
That is too broad. It can also erase true condition shorthand when a card number
is adjacent to `HP`, for example:

- `Mewtwo Gold Star (HP 103/110)...` while canonical printed HP is 80.
- `... Gyarados ... #6/102 HP` while canonical printed HP is 100.

Those numeric values are card numbers, not printed HP stats.

## V2R structured audit

On the 344-row V2R holdout:

- 60 rows were flagged as HP-stat-risk.
- 60 / 60 had canonical HP metadata.
- 58 / 60 had a fraction-safe numeric HP phrase that exactly matched the
  canonical printed HP.
- 2 / 60 did not match canonical HP and are precisely the kind of title V2 can
  over-suppress.

This means the user should not manually adjudicate the 58 structurally provable
stat cases just to teach the system that `370 HP` is a card statistic.

## Full persisted raw-sale audit

Across current persisted raw/ungraded sold evidence joined to exact canonical
card identity:

- 29,696 rows have canonical printed HP metadata.
- 1,906 rows contain a standalone `HP` token.
- 1,711 rows are structurally proven HP-stat cases because an adjacent numeric
  HP value exactly equals the canonical printed HP with fraction-safe boundaries.
- 195 rows contain `HP` but do not satisfy that structural proof.
- 62 of those unresolved rows (57 distinct titles) match V2's broad numeric-HP
  shape and therefore are specifically at risk of being wrongly suppressed by
  V2.

The 1,711 structurally proven rows form a large zero-human-labor regression
surface for HP-stat collisions.

## V3 classifier

V3 is additive and leaves V1/V2 frozen.

Frozen classifier:
- version: `pkmnprices_sold_title_condition_v3`
- blob: `e492f1990566d15fa1371a3c7576a4244d98a39b`

V3 suppresses a standalone `HP` token only when the adjacent numeric value
exactly equals the canonical card's printed HP. It does not treat card-number
fractions such as `103/110` or `6/102` as printed HP.

If canonical HP is unavailable or the number does not match, `HP` remains a
condition cue. Full text such as `Heavily Played` is never suppressed merely
because a printed HP stat also appears in the title.

## Human work is now a smaller semantic challenge set

The 344-row V2R human queue is retired for V3 validation.

A fresh V3 H1 semantic holdout was drawn after freezing V3, excluding:
- every V1 evidence ID and normalized title;
- every V2R evidence ID and normalized title;
- structurally proven canonical-HP stat titles.

The first frozen H1 sample contained 112 rows. A stronger normalization preflight
found one prior-title duplicate differing only by a trailing `[eBay]` tag.
That row was removed without replacement before any labels or V3 predictions.

Current H1R:
- 111 human-review titles.
- 0 prior evidence-ID overlap.
- 0 exact-title overlap.
- 0 stronger normalized-title overlap.
- 0 structurally proven HP-stat rows.
- 28 / 28 / 27 / 28 rows across the four price bands.
- 16 rows in each sampling stratum except DAMAGED_SINGLE, which has 15 after the
  no-replacement overlap repair.
- 69 vintage / 42 modern.
- 49 cards / 21 sets.
- sample fingerprint: `2400874f78365df02aa1e10bed77bb2e`
- sample blob: `431f23c386fd852768a0783b2c4e08fe0a7d8bd4`
- blind status: `PREDICTIONS_NOT_RUN`

This is deliberately a Stage-1 human challenge set, not a claim that 111 labels
alone are automatically sufficient for production promotion. After H1 is locked
and V3 predictions are scored, any H2 review should be limited to the classes or
failure modes whose confidence remains insufficient instead of asking the user
to label hundreds of redundant titles.

## Decision boundary

- Structural HP-stat truth: use canonical Pokemon TCG API HP metadata.
- Semantic marketplace-condition truth: retain blind human review on the smaller
  challenge set.
- Do not generate V3 predictions until the H1R human labels are frozen.
- Do not promote condition-normalized sold prices from this work alone.
