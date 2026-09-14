# inDex Fair Value F1 handoff

This handoff records available inputs; it does not begin Fair Value research.

Authoritative inputs currently available:

- Collector Appeal: final frozen `pokemon_collector_appeal_v7_expanded_price_blind_v1`, run `e282f26e-2136-4105-b0a3-f0974c4d9d70`.
- Treatment: `pokemon_card_treatment_taxonomy_v3`, fingerprint `85fdb2344d9ae7842a91bf0b3b0a434e02e99298be4cb025c8b3826066f67ddc`; diagnostic taxonomy, not a price-blind preference score.
- Pull Scarcity: accepted exact calculation-run authority where available.
- Current price: canonical latest accepted card/product price authorities with explicit observation dates.
- Structural metadata: release age, era, set, card identity, rarity, and presentation attributes.

Known gaps:

- No price-independent Treatment Preference authority.
- Grading population and broader supply are not yet normalized into date-bound, coverage-audited authorities.
- Liquidity, bid/ask depth, and transaction frequency lack a frozen cross-market authority.
- Historical Collector and Overall depth is still accumulating; do not backcast current V7 evidence.
- Cross-era price interpretation requires explicit era controls and cannot assume identical Treatment semantics.

Fair Value may use Collector Appeal as a demand-side input alongside scarcity, Treatment descriptors, age, era/set, and defensible future supply/grading/liquidity features. It must not feed learned price coefficients back into the frozen Collector Appeal authority.
