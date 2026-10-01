# Market Explorer Fix Sheet 2 — Bucket 1 evidence backlog

1. Apply the staged movement migration, build a bounded September 30 candidate,
   and prove 15/15 card Quick/Rarity 30D metrics plus non-empty Rarity and
   card Momentum before atomic promotion. Dependency: reviewed migration and
   the existing publication lease; do not run beside another writer.
2. Re-run Top/Worst and Momentum/Rarity acceptance on the candidate, including
   max-ten caps and cards/sealed filters. Preserve null 1Y until real history
   reaches the elapsed target.
3. Audit catalogue exclusions by exact reason: `NO_POSITIVE_USD_PRICE`,
   `UNRESOLVED_SET_IDENTITY`, `BULK_CONTAINER`, or
   `UNCLASSIFIED_PRODUCT_FAMILY`. Add a product only when canonical catalogue,
   set identity, and priced evidence all exist.
4. Normalize the later backend FMA response so roster size, payload-row count,
   observed-constituent count, not-collected count, offer count, and quantity
   cannot be confused. Preserve sparse-series and missing-versus-zero semantics.
5. Recheck September 30 surface freshness after the normal publisher runs.
   If it remains September 29, inspect the candidate diagnostics and lease;
   never alter `comparison_as_of` without a successfully validated generation.
