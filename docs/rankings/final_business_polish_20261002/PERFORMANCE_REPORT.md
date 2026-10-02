# Performance report

## Architectural results

| Surface | Cold/intent behavior | Warm behavior |
| --- | --- | --- |
| Era/Set paid scores | auth-resolved idle and tab intent start the exact mounted scorecard key | synchronous cache adoption; zero duplicate request |
| Set Pack Economics | static Set child modules; Sets intent and post-Set idle use `sets:pack-economics` | click joins/reads cache |
| Product Economics | page 1 only, after Product default authority and toggle intent | same request key; no all-page preload |
| Chase | Collector completes first, then Premium/save-data-gated idle page-1 prewarm | same query returns from session cache |
| Trend | one bounded response carries all four metric fields | metric switches make zero requests |

Pack Economics also has a process-local projection cache keyed by Opening fingerprint/date and Best-Open snapshot/date. Entitlement stays outside and before the shared service; the HTTP response remains private/no-store. Either publication identity invalidates the projection.

## Database shape

The Trend SQL materializes canonical snapshots once and snapshot-set/run-summary evidence once, then joins by snapshot and Set. It does not repeatedly scan run summaries and adds no index. The migration is intentionally unapplied, so a truthful production EXPLAIN and live endpoint timing are release-gate evidence, not fabricated in this code-only branch.

Browser fixture timing must separate Next dev compilation from network, backend, and render. Production-build acceptance is recorded in `ACCEPTANCE_MATRIX.md`.

Production build: 86/86 static pages generated; `/Rankings` First Load JS is 121 kB versus the 120 kB baseline. The approximately 1 kB increase is not material for the added Trend controls and prewarm orchestration.
