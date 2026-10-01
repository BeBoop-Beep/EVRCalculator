# Product data contract

## Scores

The Scores response contains identity, canonical Full Market rank/cohort size,
absolute Product Overall RIP V12, absolute Financial RIP, scalar Chase, and
inherited parent-Set Collector Appeal. Chase is the fixed, cohort-independent
0–100 transform of persisted `chase_accessibility_raw`; it is neither the raw
probability nor leader-normalized `publicScore`. There is no Product Chase rank.

## Economics

`budget_product_ranking_rows.chance_to_recover_capital` describes recovery for
the whole-unit budget strategy, which may buy many units. It is not Product
opening recovery and is not exposed as Product Economics “Recover Cost.”

Product Economics instead reads
`simulation_sealed_product_results.chance_to_recover_cost` for the exact
`sealed_product_id` and the ranking row's exact `source_calculation_run_id`.
The same exact row supplies market cost, pack count, and expected value. Missing
or mismatched evidence remains unavailable; sibling/family evidence is never
borrowed.

Public catalogue responses contain identity and facets only. They contain no
rank, scores, economics, or Best-Open fields.

Recovery probability and Chase remain distinct authorities. Recover Cost is
the exact Product simulation probability and retains small positive values
(for example, `0.000002` renders as `0.0002%`). Chase is the parent-Set-derived
fixed 0â€“100 scalar; it must never be populated from recovery probability or
from leader-normalized Set `publicScore`.
