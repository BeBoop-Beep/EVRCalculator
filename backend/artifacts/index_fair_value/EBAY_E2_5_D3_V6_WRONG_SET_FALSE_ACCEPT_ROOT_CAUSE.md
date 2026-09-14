# EBAY_E2_5 — D3-V6 WRONG_SET False-Accept Root Cause (Pre-Remediation Gate)

## Scope discipline

This task explicitly forbids redoing V5 provenance, V5 labeling, or V5
certification, and explicitly forbids creating another blind cohort until
it is established whether the three real, certified `WRONG_SET`
high-confidence false accepts are text-detectable. **This report is that
gate.** No matcher code was changed. No new cohort was captured. No
certification was re-run.

## The three real failures (from `ebay_d3_v5_fresh_blind_certification.json`)

| Row | Target | Listing title (verbatim) | Matcher state | Human class |
|---|---|---|---|---|
| `D5-0054` | Kyurem ex — Black Bolt #165 — special_illustration_rare | "Kyurem ex 165/086 NM Black Bolt Special Illustration Rare Pokemon" | HIGH_CONFIDENCE | WRONG_SET (NO) |
| `D5-0224` | Team Rocket's Mewtwo ex — Destined Rivals #231 — special_illustration_rare | "Team Rocket's Mewtwo ex 231/182 Sv10: Destined Rivals Holo" | HIGH_CONFIDENCE | WRONG_SET (NO) |
| `D5-0378` | Grafaiai — Paldea Evolved #223 — illustration_rare | "The Pokémon Company Grafaiai 223/193 Paldea Evolved English Holo IR HP 90" | HIGH_CONFIDENCE | WRONG_SET (NO) |

`_human_error_class()` maps these to `WRONG_SET` because the reviewer set
`set_consistency = INCONSISTENT`. The task name ("explicit set-identity
contradiction") presumes the title text itself contains a contradictory set
reference. **It does not, in any of the three cases.**

## Root-cause method

For each of the three false accepts, I pulled every OTHER blind-cohort row
for the exact same `canonical_card_id` (i.e., every other real eBay listing
in the 417-row cohort claiming to be the identical target card) and diffed
titles side-by-side, then downloaded and visually inspected the actual
listing photo (`image_url`, unmodified, not proxied) for the false accept
and at least one sibling true accept of the same card.

### D5-0054 vs. sibling D5-0056 (same card, both YES-pattern titles)

```
D5-0054 (NO, WRONG_SET): "Kyurem ex 165/086 NM Black Bolt Special Illustration Rare Pokemon"
D5-0056 (YES):           "Kyurem ex 165/086 - Holo Special Illustration Rare Black Bolt Pokemon Holo NM"
D5-0057 (YES):           "▸ Kyurem ex | SV: Black Bolt | Special Illustration Rare | 165/086 | NM"
D5-0059 (YES):           "Kyurem ex - Special Illustration Rare SV: Black Bolt 165/086 NM"
```

Title text is **not distinguishable** — same card name, same "165/086"
fraction, same set name "Black Bolt", same treatment wording, same
condition. Image inspection: `D5-0054`'s actual photo shows a pink/red
illustration-rare card with the ability "Grief Throw" and a completely
different Pokémon silhouette — **it is not a Kyurem card at all**.
`D5-0056`'s photo genuinely shows Kyurem (blue/ice illustration, "Blizzard
Burst"). The listing's title is a perfect textual match to the target; the
photographed item is a different, unrelated card.

### D5-0224 vs. sibling D5-0219 (same card, both YES-pattern titles)

```
D5-0224 (NO, WRONG_SET): "Team Rocket's Mewtwo ex 231/182 Sv10: Destined Rivals Holo"
D5-0219 (YES):           "SV10 Destined Rivals Team Rocket's Mewtwo ex 231/182 SIR Holo EN HP 280"
D5-0220 (YES):           "Pokemon 2025 Destined Rivals Team Rocket's Mewtwo EX SAR #231/182"
D5-0221 (YES):           "Team Rocket's Mewtwo ex Sv10 Destined Rivals 231/182 SIR Holo EN Full Art MINT"
```

Again textually indistinguishable from the true accepts. Image inspection:
`D5-0219`'s photo genuinely shows the dark red/purple "Team Rocket's Mewtwo
ex" illustration (a Rocket grunt with Mewtwo, "Power Lever" ability
visible). `D5-0224`'s photo shows a **visually distinct Mewtwo ex card** —
different color palette, different illustration style, different card —
not the Team Rocket's Mewtwo ex SIR the title claims.

### D5-0378 vs. sibling D5-0375 (same card, both YES-pattern titles)

```
D5-0378 (NO, WRONG_SET): "The Pokémon Company Grafaiai 223/193 Paldea Evolved English Holo IR HP 90"
D5-0375 (YES):           "Grafaiai 223/193 Sv02: Paldea Evolved Holo Pokemon Tcg Rare Illustration NM"
D5-0376 (YES):           "Pokémon TCG Grafaiai Scarlet & Violet Paldea Evolved Card 223/193"
D5-0377 (YES):           "Grafaiai Holo Illustration Rare SV02: Paldea Evolved 223/193 NM"
```

Same pattern. Image inspection: `D5-0375`'s photo genuinely shows Grafaiai
(green raccoon-type illustration). `D5-0378`'s photo shows **a completely
unrelated card — a Mega Charizard ex** — with its own name visible at the
top of the card art. The title text is a textbook-perfect match to the
target; the photographed card is not even the same Pokémon species.

## Finding: NOT text-detectable

All three catastrophic false accepts share the identical structural shape:

1. The listing **title** is a normal, correct, unremarkable match to the
   target card, set name, collector-number fraction, and treatment —
   indistinguishable in every observed field from 3–4 sibling listings of
   the same card that ARE genuine matches.
2. The listing's **actual photographed item is a different card entirely**
   (in one case, a different Pokémon species) — discoverable only by
   looking at the image.
3. No shared seller, no shared condition/buying-option pattern, no reused
   image hash across the three cases — each is an independent, unrelated
   seller with a mismatched photo, not a systematic seller-side or
   template-side text artifact that a rule could key on.

This is **exactly** the pre-existing, already-documented
`IMAGE_ONLY_IDENTITY_RISK` failure class from the V4 fresh-blind
certification (`D4-0375`, "Roaring Moon ex 162/131", see
`EBAY_E2_3_D3_V5_REMEDIATION_AND_NEW_BLIND_PREP.md`) — not a new failure
mode, and not evidence of a text-parsing or set-identity-contradiction gap
in the matcher's rules at all.

## Consequence for this task's explicit gate

> "do not create another blind cohort until you establish whether the
> failures are actually text-detectable."

**They are not.** Per this task's own instruction, that means:

- **No D3-V6 matcher revision should be built to chase this failure class.**
  There is no generalizable title/condition/aspect rule that distinguishes
  these three false accepts from their textually-identical true-accept
  siblings. Writing one would necessarily be a title-specific special case
  fit to exactly these three rows with zero development-partition support —
  precisely what every prior matcher revision in this repository (V3, V4,
  V5) has explicitly refused to do, for the same stated reason.
- **A new 417-row blind cohort is not warranted** as a response to this
  specific failure class, because no code change is being proposed that a
  new cohort would need to validate.
- The V5 matcher's own existing residual-limitation framing already covers
  this: image-only identity risk is a structural, irreducible property of a
  text-only matcher operating on eBay listing metadata, not a bug in the
  V5 ruleset.

## What WOULD address this class (out of scope here, flagged for awareness)

The only way to catch a title/text-perfect but image-mismatched listing is
computer-vision card recognition against the photographed item — an
entirely different system, not a text-rule "V6." That is a substantially
larger, separate initiative (image ingestion, a reference card-image
corpus, a vision-matching pipeline) and is explicitly not undertaken here.

## Explicitly not done in this task

- No `ebay_d3_matcher_v6.py` was created.
- No new blind-cohort capture script was run.
- No V5 matcher logic, thresholds, or gates were modified.
- No V5 certification was re-run.
- No V5 human labels were touched.

EBAY_D3_V6_WRONG_SET_ROOT_CAUSE_NOT_TEXT_DETECTABLE
