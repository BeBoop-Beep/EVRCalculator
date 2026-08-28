# Card Treatment Prestige V2 — Preregistered Method

## Question

“How much extra value does the market give a card just because of its treatment, once we remove the effects of Pokémon popularity and rarity/pull odds?”

Card Treatment Prestige measures how much extra market value a card receives because of its treatment, after accounting for Pokémon popularity and actual pull scarcity.

## Plain-English method

1. Observe positive Near Mint prices, using the trailing 30-day median as the primary outcome.
2. Account for which Pokémon it is.
3. Account for how difficult the card is to pull.
4. Account for the set and major mechanic subtype.
5. Compare the remaining log-price difference across treatments.
6. Convert the coefficient to an adjusted premium: `100 × (exp(beta) - 1)`.
7. Convert bootstrap effects to a comparative score: `10 × mean_j P(beta_t > beta_j)`.

Daily observations are collapsed before Study A; they are not treated as independent cards. Unknown taxonomy values and missing pull probabilities fail closed.

## Preregistered specifications and gates

Study A uses single-subject Pokémon cards:

`log(price_i) = set FE + species FE + treatment FE + log(1/pull_probability) + mechanic controls + error_i`

Study B requires same-card, same-day, Near Mint comparisons and exact printing-level pull probabilities:

`log(price_card,variant,date) = card×date FE + finish FE + log(1/pull_probability) + error`

Uncertainty is resampled by whole set for Study A and underlying card for Study B. Seed: `20260828`; production run: 1,000 draws. Broad estimates require at least 100 cards, five sets, and 20 species. Finish estimates require 50 pull-covered matched cards. Common-support coverage must be at least 50%; median sensitivity rank Spearman must be at least 0.85; sign changes or absolute log-effect movements above 0.50 are unstable. These gates were frozen before inspecting V2 coefficients.

Study A sensitivities are latest/7/30/60-day prices, demand-score rather than species controls, common-support restriction, leave-one-set-out, prior dates, top-demand exclusions, artist effects, era and supertype interactions, and within-set/scarcity-band permutation. A global score is prohibited when era heterogeneity is statistically and practically material.

## Taxonomy

`pokemon_card_treatment_taxonomy_v2` normalizes authoritative rarity, printing type, special type, and edition into a compound key. Examples include `special_illustration_rare`, `rare_holo`, `common__reverse_holo`, and `common__reverse_holo__master_ball`. Normalization contains no numeric score. Unrecognized rarity is `unmapped_treatment`; an unvalidated modifier combination is `insufficient_treatment_evidence`.

## Literature review

- Hughes, “Demand for Rarity: Evidence from a Collectible Good,” *Journal of Industrial Economics* (2022), DOI [10.1111/joie.12262](https://doi.org/10.1111/joie.12262). Peer reviewed. Motivates separating designation effects from measurable scarcity and other characteristics.
- Ghazi and Schneider, “Market value of rarity: A theory of fair value and evidence from rare baseball cards,” *Journal of Economic Behavior & Organization* (2024), DOI [10.1016/j.jebo.2024.01.016](https://doi.org/10.1016/j.jebo.2024.01.016). Peer reviewed. Supports log price, measurable rarity, close-substitute comparisons, and nonlinear scarcity relationships.
- Baro, “A Hedonic Pricing Model for Graded Pokémon Trading Cards” (2026), DOI [10.2139/ssrn.6677998](https://doi.org/10.2139/ssrn.6677998). Working paper, not presented as peer reviewed. Supports a Pokémon-specific hedonic design with set, character, rarity, artist, and market controls.

These sources determine design, not scores. Numeric results must come from the database cohort.

## Containment and promotion

V1 remains reproducible as `TREATMENT_SCORE_RULES_V1` and continues to feed `card_appeal_v1`. V2 cannot change Collector Appeal, Overall/Financial RIP, set or product rankings, or historical snapshots. A research run may be stored, but the production view resolves only the most recently explicitly approved run. Card Detail reads frozen rows; it never fits a model online and never falls back to V1 for Treatment Prestige.

## Round 2 identification representation

Research preserves raw and normalized values independently for `rarity_designation`, `printing_finish`, `special_treatment`, `edition_status`, and `mechanic_or_card_form`. The combined V2 key remains reproducible but is not assumed to be the correct regression representation. Candidate treatment effects are additive and may enter a model only when their own sample and scarcity-overlap gates pass; sparse interactions remain excluded.

The production-aligned pull authority is run scoped. Card Detail first uses the newest published `simulation_card_variant_pull_rates` run for a set and otherwise uses `pokemon_set_page_snapshot_latest.payload_json.ripDecision.sourceCalculationRunId`. `modeled_probability` is exact card-variant pack-presence probability from the authoritative V2 simulator; `effective_pull_rate` is its one-in-N representation. Card-level analytic `simulation_input_cards` values are audited separately and never substitute for missing exact printing scarcity.

The Round 1 timeout came from downloading entire set-page JSON payloads. Round 2 projects only `payload_json->ripDecision->>sourceCalculationRunId` server-side, then batches narrow reads by authoritative run ID. No new view or index is required.
