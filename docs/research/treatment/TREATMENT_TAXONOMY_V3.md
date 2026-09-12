# Treatment taxonomy V3

Status: `TREATMENT_TAXONOMY_V3_READY` for structural T2 cohort design; Treatment Preference itself remains unscored.

## Authority and grain

The production Collector authority is still frozen V7, model run `e282f26e-2136-4105-b0a3-f0974c4d9d70`, with Treatment diagnostic-only. T1 performed no production writes.

Live production does not contain `pokemon_card_treatment_scores` or its study-run table even though their additive V2 migration exists in repository history. The live structural authority is therefore canonical-card rarity plus `card_variants` finish/special/edition metadata, joined at exact variant grain. `card_variants` has a natural uniqueness constraint over card, printing type, special type and edition. Exact pull evidence is variant/run-grained and remains a separate diagnostic authority.

## Census

Current frozen-V7 cohort: 18,293 canonical cards. V2 mapped 15,788 and left 2,505 unmapped. V3 structurally maps 18,040 and leaves 253 explicit unresolved rows: 250 unsupported legacy structures and three missing-source-metadata rows. No unknown non-null label was silently mapped, so the ambiguous count is zero. Associated variant census: 33,148 variants, of which 32,904 map from available structural metadata.

Full era, label, set, variant and unresolved-card detail is machine-readable in the coverage and unresolved artifacts. The 253 remaining rows are intentionally not collapsed into `other`.

## Ontology contract

Each result preserves an era-local label and zero or more semantic attributes. Attributes are descriptive and non-ordinal: illustration-led, full/extended/alternate art, texture, gold/gilded, rainbow, shiny, holo/reverse/special foil, gallery styles, frame styles, character scene, subset/vintage/promo status and mechanic-bound presentation. Detection is deterministic from rarity, printing type, special type and edition. Attributes lacking explicit metadata remain unassigned. No manual override was needed in V3; the registry is versioned and empty.

“Rare Secret” is deliberately era-qualified. Black & White secret treatments are not globally equated with XY, Sun & Moon, Sword & Shield or vintage secret cards. LV.X, Gold Star, Prime, LEGEND, BREAK, GX, V/VMAX/VSTAR, Amazing Rare, Radiant, ACE SPEC and Mega Attack Rare remain era-local mechanic/presentation bundles.

Rarity is the publisher/API designation. Treatment is physical or visual presentation. Pull Scarcity is modeled probability. A row may share one while differing on the others; none is substituted for another.

## Comparability and T2 cohorts

The frozen extraction found two Tier-A same-canonical, scarcity-near contrasts, 6,251 Tier-B same-subject/set/era contrasts, and 87 scarcity-matched contrasts at ratio ≤1.25. Exact cohort fingerprints and all source calculation-run IDs are stored in `treatment_t2_research_cohorts.json`. Price was neither queried nor used for membership.

Pair edges are direct only when same-card evidence exists and local when same-subject evidence exists. Connectivity never licenses transitive preference claims. Unsupported absent edges stay unsupported; an empty observed edge is not interpreted as equivalence.

Strongest next opportunities are identical-card finish/edition contrasts and same-subject, same-set comparisons with close pull probability. Limitations remain: only two Tier-A cases, partial exact-pull coverage, source rarity conflation, absent artwork-identity fields, and no price-independent preference responses. T2 must preserve these limits and must not infer preference from taxonomy membership.
