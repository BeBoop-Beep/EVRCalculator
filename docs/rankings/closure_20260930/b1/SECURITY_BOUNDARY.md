# Bucket 1 security boundary

## Public allowlists

Era headline: identity, modeled Set count, Overall score/rank/cohort/tier/status/reason, market date, publication identity, benchmark key/calibration/model version, and reference metadata.

Set headline: identity, Era identity, logo/symbol, Overall score/rank/cohort/tier/status/reason, market date, publication identity, benchmark key/calibration/model version, and reference metadata.

Set Pack Economics preview: Set/Era identity, logo/symbol, product-family count, product count, average pack cost per pack, and opening-economics date.

Product catalogue: Product ID/name/type/family classification/artwork, Set identity, Era identity, and route identity. Ordering is alphabetical and independent of scores.

## Protected fields

Financial/Collector/Chase component scores and ranks, Product ranks/scores/tiers, price and economics values, Best-Open, expected value, modeled return, recover-cost probability, entertainment cost, histories, lineage, and private authority identifiers do not appear in the public contracts.

The wide `/tcgs/pokemon/rankings/scorecards`, detailed `/tcgs/pokemon/rankings/pack-economics`, `/explore/product-rankings/scores`, and `/explore/product-rankings/economics` endpoints retain their server-side entitlement gates. HTTP tests prove anonymous and base requests are rejected before scorecard or detailed-Pack database work.

## Cache and downgrade safety

Public and paid reads have distinct cache keys. The Rankings cache identity includes live user/access identity. On downgrade, Set paid scorecards and detailed Pack state are cleared, Product paid states are cleared, and render selection switches to the independently loaded public catalogue. No paid payload is used as a fallback for anonymous family facets or rows.

The live serialized public contracts were scanned for protected field names; result: zero hits.
